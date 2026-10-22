"""Task-owned native comparison, repeated jobs and control/data checks."""
from copy import deepcopy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sensor_visualizer_v07.contracts import load_job,write_json
from sensor_visualizer_v07.control_ipc import request
from sensor_visualizer_v07.trajectory import TrajectoryRecorder
from sensor_visualizer_v07.capture_supervisor import CaptureSupervisor

class Validation:
    def __init__(self):
        self.output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation')/datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output.mkdir(parents=True,exist_ok=False)
        self.report={'state':'starting','directory':str(self.output),'pid':os.getpid(),'results':[],
                     'started_utc':datetime.now(timezone.utc).isoformat(),
                     'gui':os.environ.get('SV07_VALIDATION_GUI')=='1'}
        self.children=[];self.owner=None;self.monitor_stop=threading.Event();self.metrics=[];self.receipt_ids=set()
    def status(self,phase,**values):
        self.report.update(phase=phase,updated_ns=time.monotonic_ns(),**values)
        write_json(ROOT/'reports/native_validation_status.json',self.report)
    def spawn(self,command,directory,env=None):
        with (directory/'kit.log').open('ab') as log:
            process=subprocess.Popen(command,cwd=directory,env=env,stdin=subprocess.DEVNULL,
                                     stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.children.append(process);return process
    def until(self,predicate,timeout=180):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            value=predicate()
            if value:return value
            time.sleep(.1)
        raise TimeoutError('Validation timeout in '+self.report['phase'])
    def rpc(self,action,payload=None):
        return request(self.socket,{'action':action,'payload':payload or {},'command_id':uuid.uuid4().hex},timeout=2)
    def applied(self,action,payload=None):
        accepted=self.rpc(action,payload)
        def check():
            rows=request(self.socket,{'action':'status'},timeout=2).get('receipts',[])
            found=next((r for r in rows if r['command_id']==accepted['command_id']),None)
            if found and found['state']!='applied':raise RuntimeError(str(found))
            return found
        return self.until(check,30)
    def start_owner(self,version):
        project=ROOT.parent/version;directory=self.output/version;directory.mkdir(exist_ok=True)
        job=load_job(overrides={'output_directory':str(directory),'mode':'interactive',
            'interactive':{'diagnostics_enabled':True},'runtime':{'interactive_gpu':'0'},
            'diagnostics':{'level':'basic','slow_stage_ms':100}})
        job_path=directory/'owner_job.json';write_json(job_path,job)
        env=os.environ.copy()
        if self.report['gui']:
            displays=list(Path('/tmp/.X11-unix').glob('X*'))
            if len(displays)!=1:raise RuntimeError('Identify one desktop display before GUI validation')
            env['DISPLAY']=':'+displays[0].name[1:]
        self.socket=str(directory/'runtime/engine.sock')
        env['SV'+version[1:]+'_SOCKET']=self.socket
        env['SV'+version[1:]+'_OWNER_TEST']='3600'
        self.owner=self.spawn(['/usr/bin/python3',str(project/'run_capture.py'),
                              '--interactive' if self.report['gui'] else '--headless-owner',
                              '--job',str(job_path),'--gpu','0'],directory,env)
        def ready():
            if self.owner.poll() is not None:raise RuntimeError('Owner exited; inspect '+str(directory/'kit.log'))
            try:
                state=request(self.socket,{'action':'status'},timeout=.5)
                if state.get('phase')=='failed':raise RuntimeError(state.get('error'))
                return state if state.get('phase')=='interactive_ready' else None
            except (OSError,EOFError):return None
        state=self.until(ready)
        self.monitor_stop.clear();self.monitor_thread=threading.Thread(target=self.monitor,args=(version,),daemon=True);self.monitor_thread.start()
        self.applied('play');return state,directory
    def monitor(self,version):
        while not self.monitor_stop.is_set():
            try:
                state=request(self.socket,{'action':'status'},timeout=.5)
                row={'version':version,'phase':self.report['phase'],'monotonic_ns':time.monotonic_ns(),
                     'statistics':state.get('statistics'),'input_status':state.get('input_status'),'receipts':[]}
                for receipt in state.get('receipts',[]):
                    if receipt['command_id'] not in self.receipt_ids:
                        self.receipt_ids.add(receipt['command_id']);row['receipts'].append(receipt)
                self.metrics.append(row)
                # Keep key state fresh even during long renders in the other process.
                self.rpc('keys',{'source':'validation','keys':['W','U'] if int(time.monotonic())%4<2 else []})
            except Exception as exc:
                self.metrics.append({'version':version,'phase':self.report['phase'],'error':str(exc),'monotonic_ns':time.monotonic_ns()})
            self.monitor_stop.wait(.1)
    def trajectory(self,state,directory,groups=8):
        path=directory/'reference_trajectory'
        recorder=TrajectoryRecorder(path,state['metadata'])
        source=state['capture_snapshot']
        for i in range(groups):
            row=deepcopy(source);row.update(t_sim_s=i/10,state_revision=i,snapshot_id=uuid.uuid4().hex)
            row['position_world_m'][0]+=.01*i
            recorder.append(row)
        recorder.close();return path
    def stop_owner(self):
        self.monitor_stop.set();self.monitor_thread.join(timeout=3)
        try:self.rpc('keys',{'source':'validation','keys':[]});self.rpc('close')
        except Exception:pass
        try:self.owner.wait(timeout=30)
        except subprocess.TimeoutExpired:self.owner.terminate();self.owner.wait(timeout=15)
    def baseline(self):
        self.status('v06_owner_start')
        state,directory=self.start_owner('v06');trajectory=self.trajectory(state,directory)
        for gpu in ('0','1'):
            phase='v06_gpu'+gpu;self.status(phase);task=directory/phase;task.mkdir()
            job=load_job(overrides={'output_directory':str(task),'groups':8,'preview':{'enabled':False},
                'replay':{'mode':'offline','trajectory':str(trajectory),'socket':self.socket,
                          'control_path':str(task/'control.json'),'status_path':str(task/'status.json')}})
            path=task/'job.json';write_json(path,job);write_json(task/'control.json',{'action':'run'})
            start=time.monotonic()
            child=self.spawn(['/usr/bin/python3',str(ROOT.parent/'v06/run_capture.py'),'--job',str(path),
                             '--entry',str(ROOT.parent/'v06/kit_replay_entry.py'),'--gpu',gpu],task)
            code=child.wait(timeout=600)
            result=json.loads((task/'status.json').read_text())
            if code or result['state']!='finished':raise RuntimeError('Baseline capture failed: '+str(result))
            self.report['results'].append({'case':phase,'total_wall_s':time.monotonic()-start,**result})
            self.status(phase+'_finished')
        self.stop_owner()
    def wait_task(self,supervisor,token,timeout=600):
        def check():
            rows=supervisor.status();row=next(r for r in rows if r['task_id']==token)
            self.status(self.report['phase'],active_task=row)
            if row.get('state')=='failed':raise RuntimeError('Task failed: '+str(row))
            return row if not row['running'] and row.get('job_complete') else None
        return self.until(check,timeout)
    def v07(self):
        self.status('v07_owner_start')
        state,directory=self.start_owner('v07');trajectory=self.trajectory(state,directory,100)
        supervisor=CaptureSupervisor(ROOT,directory,self.socket)
        try:
            self.status('v07_prepare_service');start=time.monotonic();supervisor.ensure_worker()
            def worker_ready():
                state=supervisor.worker_status()
                if state['phase']=='not_running':raise RuntimeError('Capture worker exited; inspect capture_service.log')
                return state if state['phase']=='idle' else None
            worker=self.until(worker_ready,600)
            self.report['worker_prepare_s']=time.monotonic()-start;self.report['worker_id']=worker['worker_id']
            for name,groups in (('resident_first',8),('resident_repeat',3)):
                self.status(name);start=time.monotonic()
                task=supervisor.start({'mode':'offline','trajectory':str(trajectory),'groups':groups,'ros_preview':False})
                result=self.wait_task(supervisor,task['task_id'])
                self.report['results'].append({'case':name,'total_wall_s':time.monotonic()-start,**result})
                same=supervisor.worker_status();assert same['worker_id']==worker['worker_id'] and same['phase']=='idle'
                assert not supervisor.resource_busy()
            self.status('pause_resume_stop')
            task=supervisor.start({'mode':'offline','trajectory':str(trajectory),'groups':8,'ros_preview':False})
            self.until(lambda:next((x for x in supervisor.status() if x['task_id']==task['task_id'] and x.get('groups',0)>=1),None))
            supervisor.control(task['task_id'],'pause')
            paused=self.until(lambda:next((x for x in supervisor.status() if x['task_id']==task['task_id'] and x['state']=='paused'),None))
            time.sleep(.5);assert next(x for x in supervisor.status() if x['task_id']==task['task_id'])['groups']==paused['groups']
            supervisor.control(task['task_id'],'run');time.sleep(.5);supervisor.control(task['task_id'],'stop')
            result=self.wait_task(supervisor,task['task_id']);assert result['stopped']
            self.report['results'].append({'case':'pause_resume_stop',**result})
            self.status('live_latest')
            task=supervisor.start({'mode':'live_latest','groups':3,'ros_preview':True})
            result=self.wait_task(supervisor,task['task_id']);self.report['results'].append({'case':'live_latest',**result})
            self.status('live_complete');self.applied('record_start')
            task=supervisor.start({'mode':'live_complete','groups':3,'ros_preview':False})
            time.sleep(4);self.applied('record_stop')
            result=self.wait_task(supervisor,task['task_id']);self.report['results'].append({'case':'live_complete',**result})
            self.status('hundred_groups')
            task=supervisor.start({'mode':'offline','trajectory':str(trajectory),'groups':100,'ros_preview':False})
            result=self.wait_task(supervisor,task['task_id'],3600)
            self.report['results'].append({'case':'hundred_groups',**result})
            self.status('web_restart_and_restore')
            recovered=CaptureSupervisor(ROOT,directory,self.socket)
            assert not any(r['running'] for r in recovered.status()) and not recovered.resource_busy()
            self.applied('stop');self.applied('play');self.applied('exit');self.applied('reinitialize');self.applied('play')
        finally:
            try:
                for row in supervisor.status():
                    if row['running']:supervisor.control(row['task_id'],'stop');self.wait_task(supervisor,row['task_id'])
                supervisor.close_worker()
                self.until(lambda:supervisor.worker_status().get('phase') in ('closed','not_running'),60)
            finally:self.stop_owner()
    def run(self):
        try:
            if os.environ.get('SV07_SKIP_BASELINE')=='1':
                self.report['baseline_skipped']='Prior same-instance baseline retained separately; this run validates v07'
            else:self.baseline()
            self.v07();self.status('data_validation')
            for result in self.report['results']:
                if result.get('session') and result.get('groups',0):
                    command=['/bin/bash','--noprofile','--norc','-c',
                             'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B "$@"','sv07-validate',
                             str(ROOT/'tools/validate_capture_data.py'),result['session']]
                    p=subprocess.run(command,capture_output=True,text=True,timeout=300)
                    if p.returncode:raise RuntimeError('MCAP validation failed: '+p.stderr[-3000:])
                    result['data_validation']=json.loads(p.stdout.split('VALIDATION_JSON=')[-1])
            self.report['state']='passed';self.status('finished')
        except Exception:
            self.report['state']='failed';self.status('failed',error=traceback.format_exc());traceback.print_exc()
        finally:
            self.monitor_stop.set()
            # The worker is launched by the supervisor rather than spawn().
            # Stop only the recorded native process belonging to this test run.
            launch=self.output/'v07/runtime/capture_launch.json'
            if launch.exists():
                try:
                    info=json.loads(launch.read_text());pid=info['pid']
                    raw=Path('/proc',str(pid),'cmdline').read_bytes()
                    if CaptureSupervisor.start_ticks(pid)==info['start_ticks'] and str(ROOT/'kit_service_entry.py').encode() in raw:
                        import signal
                        os.kill(pid,signal.SIGTERM)
                        self.report.setdefault('cleanup',[]).append({'pid':pid,'action':'terminate_owned_worker','reason':'validation finally'})
                except (OSError,ValueError,KeyError):pass
            for child in self.children:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=15)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
            with (self.output/'owner_metrics.jsonl').open('w') as stream:
                for row in self.metrics:stream.write(json.dumps(row)+'\n')
            write_json(ROOT/'reports/native_validation_result.json',self.report)
            write_json(self.output/'validation_result.json',self.report)

if __name__=='__main__':Validation().run()
