"""Web-side ownership of capture children, independent from the interactive Kit."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from .contracts import DEFAULT,load_job,write_json,merge
from .capture_plan import make_plan,request_options
from .trajectory import Trajectory
from .offline_job import snapshot_trajectory
from .scene_replay import scene_selection,recorded_interface

class CaptureSupervisor:
    def __init__(self,project,output,socket_path):
        self.project,self.output,self.socket=Path(project),Path(output),str(socket_path)
        self.tasks={};self.lock=threading.Lock()
        for p in (self.output/'tasks').glob('*/task.json'):
            try:
                info=json.loads(p.read_text())
                if info.get('project')!=str(self.project.resolve()):continue
                self.tasks[p.parent.name]={'process':None,'pid':info['pid'],'start_ticks':info['start_ticks'],
                    'directory':p.parent,'mode':info['mode'],'created':info['created'],'capture_plan':info.get('capture_plan'),
                    'scene_selection':info.get('scene_selection')}
            except (OSError,ValueError,KeyError):continue
    @staticmethod
    def start_ticks(pid):
        try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except (OSError,IndexError):return None
    def alive(self,task):
        if task['process'] is not None:return task['process'].poll() is None
        if self.start_ticks(task['pid'])!=task['start_ticks']:return False
        try:
            raw=Path('/proc',str(task['pid']),'cmdline').read_bytes()
            return str(self.project/'kit_replay_entry.py').encode() in raw
        except OSError:return False
    def resource_busy(self):
        """The inherited capture lease can outlive recovered argv visibility."""
        import fcntl
        path=self.output/'runtime/capture.lock'
        try:
            with path.open('rb') as stream:
                try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return True
        except FileNotFoundError:pass
        return False
    def _source(self,payload):
        if payload.get('mode','offline')!='offline':raise ValueError('single0602 requires a closed offline trajectory')
        request_options(payload,DEFAULT['physics_hz'])
        if not payload.get('trajectory'):raise ValueError('Select a completed trajectory')
        path=Path(payload['trajectory']).resolve()
        if not path.is_relative_to(self.output.resolve()):raise ValueError('Trajectory outside project output')
        return path,Trajectory.load(path)
    def preview(self,payload):
        path,trajectory=self._source(payload)
        selection=scene_selection(payload,trajectory.metadata,check_files=payload.get('scene_policy')=='environment')
        if selection['scene_policy']=='environment':recorded_interface(trajectory.metadata,self.project)
        return {'trajectory':str(path),'capture_plan':make_plan(trajectory.duration,payload,DEFAULT['physics_hz']),
                'scene_selection':selection,'interface_check':'performed in Headless before capture products and writer start'}
    def start(self,payload):
        with self.lock:
            if any(self.alive(x) for x in self.tasks.values()):raise ValueError('One active capture per supervisor; finish or stop it first')
            if self.resource_busy():raise ValueError('Previous capture resources are still releasing; wait for cleanup to finish')
            requested_device=None
            if payload.get('gpu') not in (None,''):
                from .gpu_config import resolve_gpu
                requested_device=resolve_gpu(payload['gpu'])
            mode='offline';source,trajectory=self._source(payload);metadata=trajectory.metadata
            selection=scene_selection(payload,metadata,check_files=payload.get('scene_policy')=='environment')
            if selection['scene_policy']=='environment':recorded_interface(metadata,self.project)
            plan=make_plan(trajectory.duration,payload,DEFAULT['physics_hz'])
            token=uuid.uuid4().hex[:12];directory=self.output/'tasks'/token;path=str(directory/'trajectory')
            policy_path=self.project/'config/capture_policy.json'
            policy=json.loads(policy_path.read_text()) if policy_path.exists() else {}
            if set(policy)-{'capture','scheduling','diagnostics','pipeline'}:raise ValueError('Unsupported capture policy field')
            sensors=(metadata.get('sensors_selection',{}) if selection['sensor_policy']=='recorded' else payload.get('sensors',{}))
            job=load_job(overrides=merge(policy,{'scene':selection['target_scene'],'groups':plan['planned_groups'],'capture_plan':plan,
                'sample_hz':plan['sample_hz'],'mode':'offline',
                'sensors':sensors,
                'output_directory':str(self.output),'preview':{'enabled':bool(payload.get('ros_preview',False))},
                'render':selection['render'],
                'replay':{'mode':mode,'trajectory':path,'control_path':str(directory/'control.json'),
                          'scene_policy':selection['scene_policy'],'sensor_policy':selection['sensor_policy'],'placement':selection['placement'],
                          'status_path':str(directory/'status.json')}}))
            profile_id=(payload.get('asset_profile_id') or metadata.get('asset_profile_id') or
                        metadata.get('asset_manifest',{}).get('asset_profile',{}).get('id'))
            if profile_id:job['asset_profile_id']=profile_id
            job['device_assignment']={'role':'formal_capture','requested':requested_device,
                'binding_scope':'Kit renderer/activeGpu and physics/cudaDevice; actual RTX/CUDA execution requires native/device evidence'}
            # Revalidate and plan from the exact private source the child will read.
            directory.mkdir(parents=True)
            try:
                trajectory=snapshot_trajectory(source,directory/'trajectory')
                selection=scene_selection(payload,trajectory.metadata,check_files=payload.get('scene_policy')=='environment')
                if selection['scene_policy']=='environment':recorded_interface(trajectory.metadata,self.project)
                plan=make_plan(trajectory.duration,payload,job['physics_hz'])
                job.update(groups=plan['planned_groups'],capture_plan=plan,scene=selection['target_scene'],
                           render=merge(DEFAULT['render'],selection['render']))
                job['replay'].update(scene_policy=selection['scene_policy'],placement=selection['placement'])
                job=load_job(overrides=job)
                jobpath=directory/'job.json';write_json(jobpath,job);write_json(directory/'control.json',{'action':'run'})
            except Exception as exc:
                write_json(directory/'status.json',{'state':'failed','completion_reason':'failed','error':str(exc)})
                raise
            command=[sys.executable,str(self.project/'run_capture.py'),'--job',str(jobpath),'--entry',str(self.project/'kit_replay_entry.py')]
            if requested_device:command+=['--gpu',requested_device['uuid']]
            # An inherited advisory lock survives a web-service restart.
            import fcntl
            lockfile=self.output/'runtime/capture.lock';lockfile.parent.mkdir(parents=True,exist_ok=True)
            capture_lock=lockfile.open('a')
            try:
                try:fcntl.flock(capture_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise ValueError('Another owned capture is still active')
                log=(directory/'kit.log').open('ab')
                try:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                    start_new_session=True,pass_fds=(capture_lock.fileno(),))
                finally:log.close()
            except Exception as exc:
                write_json(directory/'status.json',{'state':'failed','completion_reason':'failed','capture_plan':plan,'error':str(exc)})
                raise
            finally:capture_lock.close()
            created=datetime.now().isoformat();ticks=self.start_ticks(process.pid)
            self.tasks[token]={'process':process,'pid':process.pid,'start_ticks':ticks,'directory':directory,'mode':mode,'created':created,'capture_plan':plan,'scene_selection':selection}
            write_json(directory/'task.json',{'project':str(self.project.resolve()),'pid':process.pid,'start_ticks':ticks,'mode':mode,'created':created,'capture_plan':plan,'scene_selection':selection})
            return {'task_id':token,'pid':process.pid,'mode':mode,'directory':str(directory),'state':'starting','capture_plan':plan,'scene_selection':selection}
    def control(self,token,action):
        if action not in ('run','pause','stop'):raise ValueError('Invalid task action')
        with self.lock:
            task=self.tasks[token]
            if not self.alive(task):raise ValueError('Task already exited')
            write_json(task['directory']/'control.json',{'action':action})
        return {'state':'queued','action':action,'boundary':'next complete capture group'}
    def status(self):
        out=[]
        with self.lock:
            for token,x in self.tasks.items():
                running=self.alive(x)
                row={'task_id':token,'pid':x['pid'],'groups':0,'exit_code':x['process'].poll() if x['process'] else None,
                    'running':running,'exit_code_known':x['process'] is not None,'mode':x['mode'],'created':x['created']}
                if x.get('capture_plan'):
                    row.update(capture_plan=x['capture_plan'],planned_groups=x['capture_plan']['planned_groups'],written=0)
                if x.get('scene_selection'):row['scene_selection']=x['scene_selection']
                p=x['directory']/'status.json'
                if p.exists():
                    try:row.update(json.loads(p.read_text()))
                    except (OSError,json.JSONDecodeError):row['state']='status_updating'
                else:row['state']='starting'
                row.update(process_exited=not running,resource_lock_released=not self.resource_busy())
                if not running and row.get('state') not in ('finished','failed'):row.update(state='failed',completion_reason='failed',error='Capture process exited; see task kit.log')
                out.append(row)
            # Recovered argv-based liveness and inherited lock release are
            # separate observations. Do not present the gap as capture-ready.
            if out and not any(x['running'] for x in out) and self.resource_busy():
                newest=max(out,key=lambda x:x['created'])
                newest.update(cleanup_pending=True,state='releasing_resources')
        return out
