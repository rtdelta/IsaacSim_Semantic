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
from .contracts import load_job,write_json
from .control_ipc import request
from .trajectory import Trajectory

class CaptureSupervisor:
    def __init__(self,project,output,socket_path):
        self.project,self.output,self.socket=Path(project),Path(output),str(socket_path)
        self.tasks={};self.lock=threading.Lock()
        for p in (self.output/'tasks').glob('*/task.json'):
            try:
                info=json.loads(p.read_text())
                if info.get('project')!=str(self.project.resolve()):continue
                self.tasks[p.parent.name]={'process':None,'pid':info['pid'],'start_ticks':info['start_ticks'],
                    'directory':p.parent,'mode':info['mode'],'created':info['created']}
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
    def start(self,payload):
        with self.lock:
            if any(self.alive(x) for x in self.tasks.values()):raise ValueError('One active capture per supervisor; finish or stop it first')
            mode=payload['mode'];metadata=None;path=payload.get('trajectory')
            if mode not in ('offline','live_latest','live_complete'):raise ValueError('Unknown capture mode')
            if mode=='offline':
                p=Path(path).resolve()
                if not p.is_relative_to(self.output.resolve()):raise ValueError('Trajectory outside project output')
                trajectory=Trajectory.load(p);metadata=trajectory.metadata;path=str(p)
                if not metadata.get('recording_complete'):raise ValueError('End trajectory recording before offline capture')
            else:
                state=request(self.socket,{'action':'status'})
                if state.get('phase')!='interactive_ready':raise ValueError('Initialize interactive owner first')
                metadata=state['metadata']
                if mode=='live_complete':
                    if not state['recording']:
                        request(self.socket,{'action':'record_start'})
                        deadline=time.monotonic()+5
                        while time.monotonic()<deadline:
                            state=request(self.socket,{'action':'status'})
                            if state.get('recording'):break
                            time.sleep(.05)
                        if not state.get('recording'):raise TimeoutError('Trajectory did not start')
                    path=state['trajectory_path']
            token=uuid.uuid4().hex[:12];directory=self.output/'tasks'/token;directory.mkdir(parents=True)
            job=load_job(overrides={'scene':metadata['scene'],'groups':int(payload.get('groups',100)),
                'sample_hz':float(payload.get('sample_hz',10)),'mode':'offline',
                'output_directory':str(self.output),'preview':{'enabled':bool(payload.get('ros_preview',True))},
                'render':metadata.get('render',{}),
                'replay':{'mode':mode,'trajectory':path,'socket':self.socket,'control_path':str(directory/'control.json'),
                          'status_path':str(directory/'status.json')}})
            if mode=='offline':job['groups']=min(job['groups'],int(trajectory.duration*job['sample_hz']+1e-7)+1)
            jobpath=directory/'job.json';write_json(jobpath,job);write_json(directory/'control.json',{'action':'run'})
            command=[sys.executable,str(self.project/'run_capture.py'),'--job',str(jobpath),'--entry',str(self.project/'kit_replay_entry.py')]
            if payload.get('gpu'):command+=['--gpu',str(payload['gpu'])]
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
            finally:capture_lock.close()
            created=datetime.now().isoformat();ticks=self.start_ticks(process.pid)
            self.tasks[token]={'process':process,'pid':process.pid,'start_ticks':ticks,'directory':directory,'mode':mode,'created':created}
            write_json(directory/'task.json',{'project':str(self.project.resolve()),'pid':process.pid,'start_ticks':ticks,'mode':mode,'created':created})
            return {'task_id':token,'pid':process.pid,'mode':mode,'directory':str(directory),'state':'starting'}
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
                row={'task_id':token,'pid':x['pid'],'exit_code':x['process'].poll() if x['process'] else None,
                    'running':running,'exit_code_known':x['process'] is not None,'mode':x['mode'],'created':x['created']}
                p=x['directory']/'status.json'
                if p.exists():
                    try:row.update(json.loads(p.read_text()))
                    except (OSError,json.JSONDecodeError):row['state']='status_updating'
                else:row['state']='starting'
                if not running and row.get('state') not in ('finished','failed'):row.update(state='failed',error='Capture process exited; see task kit.log')
                out.append(row)
        return out
