"""One resident Kit owner; short job leases and independent worker lifetime."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
from .contracts import load_job,write_json
from .control_ipc import ControlEndpoint
from .diagnostics import RunDiagnostics

def compatibility_key(job):
    path=Path(job['scene'])
    assets=[str(path.resolve()),hashlib.sha256(path.read_bytes()).hexdigest()]
    values={name:job[name] for name in ('physics_hz','render','sensors')}
    values['backend']=job['capture']['backend']
    return hashlib.sha256(json.dumps([assets,values],sort_keys=True).encode()).hexdigest()

class CaptureService:
    def __init__(self,project,job):
        self.project=Path(project).resolve();self.job=job;self.output=Path(job['output_directory']).resolve()
        self.runtime=self.output/'runtime';self.runtime.mkdir(parents=True,exist_ok=True)
        self.worker_id=uuid.uuid4().hex;self.scene=None;self.key=None;self.pending=None;self.active=None
        self.mutex=threading.RLock();self.shutdown_requested=False;self.phase='loading';self.job_lease=None
        self.diag=RunDiagnostics(self.output,job['diagnostics'],self.project)
        self.diag.context(worker_id=self.worker_id,role='capture_service',group_id=None)
        self.diag.start_resources()
        import fcntl
        self.worker_lease=(self.runtime/'capture_worker.lock').open('a')
        try:fcntl.flock(self.worker_lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.worker_lease.close();self.diag.close();raise RuntimeError('Resident capture worker already exists')
        self.endpoint=ControlEndpoint(self.runtime/'capture.sock',on_request=self.admit)
        self.heartbeat=None
        self.info={'worker_id':self.worker_id,'pid':os.getpid(),'project':str(self.project),
                   'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]}
        write_json(self.runtime/'capture_worker.json',self.info)
        self.publish()

    def publish(self,**extra):
        with self.mutex:
            value={**self.info,'phase':self.phase,'heartbeat_ns':time.monotonic_ns(),
                   'pending_job':self.pending.name if self.pending else None,
                   'active_job':self.active.spec.get('job_id') if self.active else None,
                   'device':getattr(getattr(self.scene,'drivers',None),'binding',None),**extra}
            self.endpoint.publish(value)
        write_json(self.runtime/'capture_worker_status.json',value)

    def admit(self,message):
        """Runs on the socket thread: admission/file leases only, never Kit calls."""
        import fcntl
        with self.mutex:
            action=message.get('action')
            if action=='shutdown':
                if self.pending or self.active:raise ValueError('Stop and drain the current job before closing the service')
                self.shutdown_requested=True;return {'state':'queued','action':'shutdown'}
            if action!='start':raise ValueError('Unknown capture service command')
            if self.phase!='idle' or self.pending or self.active or self.shutdown_requested:
                raise ValueError('Capture service is not idle; wait for startup or drain')
            path=Path(message['job_path']).resolve()
            if not path.is_relative_to(self.output/'tasks') or path.name!='job.json':raise ValueError('Invalid owned job path')
            candidate=load_job(path)
            if Path(candidate['output_directory']).resolve()!=self.output:raise ValueError('Job output differs from service')
            requested=candidate.get('device_assignment',{}).get('requested')
            actual=getattr(self.scene.drivers,'binding',{}).get('requested') if self.scene else None
            if requested and actual and requested['uuid']!=actual['uuid']:
                raise ValueError('Close the idle service before selecting a different capture GPU')
            lease=(self.runtime/'capture.lock').open('a')
            try:fcntl.flock(lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                lease.close();raise ValueError('Another capture owns the job lease')
            self.job_lease=lease;self.pending=path;self.phase='preparing_job'
            self.diag.event('job_admitted',critical=True,job_id=candidate['replay']['job_id'],job_path=str(path))
            return {'state':'accepted','worker_id':self.worker_id,'pid':os.getpid()}

    async def ensure_scene(self,job):
        from .scene import SceneStepper
        key=await asyncio.to_thread(compatibility_key,job)
        if self.scene and key==self.key and self.scene.reusable():
            self.diag.event('worker_scene_compatible',critical=True,stage_generation=self.scene.generation)
            return
        self.phase='loading';self.publish()
        if self.scene:
            self.scene.bind_diagnostics(self.diag)
            with self.diag.span('worker_scene_rebuild_close'):await self.scene.close()
        self.scene=SceneStepper(self.project,job,self.diag)
        self.diag.attach_kit(self.scene.app)
        with self.diag.span('worker_scene_load_and_warm'):await self.scene.initialize()
        self.scene.job=job;self.key=key
        self.diag.event('worker_scene_ready',critical=True,key=key,registry=self.scene.registry)

    async def heartbeat_loop(self):
        while not self.shutdown_requested or self.active:
            self.publish();await asyncio.sleep(.5)

    async def run(self):
        from .replay_capture import ReplayCapture
        self.heartbeat=asyncio.create_task(self.heartbeat_loop())
        try:
            await self.ensure_scene(self.job)
            self.phase='idle';self.publish();print('[SV07 CAPTURE SERVICE READY]',flush=True)
            while not self.shutdown_requested:
                with self.mutex:path=self.pending
                mailbox=self.runtime/'capture_pending.json'
                if path is None and mailbox.exists():
                    submission=json.loads(mailbox.read_text())
                    self.admit({'action':'start','job_path':submission['job_path']})
                    path=self.pending
                if path is None:await asyncio.sleep(.02);continue
                job=load_job(path)
                try:
                    await self.ensure_scene(job)
                    self.diag.detach_kit()
                    self.active=ReplayCapture(self.project,job,scene=self.scene,worker_id=self.worker_id,
                                              on_status=lambda status:self.publish(job_status=status))
                    with self.mutex:self.pending=None;self.phase='running'
                    code=await self.active.run()
                    if code:self.scene.capture_failed=True
                    terminal=dict(self.active.status)
                    terminal.update(worker_reusable=self.scene.reusable(),job_complete=True)
                    self.diag.event('worker_job_closed',critical=True,job_id=job['replay']['job_id'],exit_code=code,
                                    groups=self.active.groups,worker_reusable=terminal['worker_reusable'])
                except Exception as exc:
                    import traceback
                    terminal={'state':'failed','error':str(exc),'job_complete':True,'worker_reusable':False}
                    self.diag.warning('worker_job_failed',traceback.format_exc())
                    if self.scene:self.scene.capture_failed=True
                finally:
                    if self.scene:
                        self.scene.bind_diagnostics(self.diag)
                        self.scene.on_phase=None
                        self.diag.attach_kit(self.scene.app)
                    with self.mutex:
                        self.active=None;self.pending=None
                        if self.job_lease:self.job_lease.close();self.job_lease=None
                        self.phase='idle'
                    write_json(job['replay']['status_path'],terminal)
                    if mailbox.exists():
                        submission=json.loads(mailbox.read_text())
                        if submission['job_id']==job['replay']['job_id']:mailbox.unlink()
                    self.publish(last_job=job['replay']['job_id'],last_result=terminal)
        finally:
            self.phase='closing';self.publish()
            if self.heartbeat:self.heartbeat.cancel();await asyncio.gather(self.heartbeat,return_exceptions=True)
            try:
                if self.scene:
                    self.scene.bind_diagnostics(self.diag);await self.scene.close()
            finally:
                self.diag.detach_kit();await asyncio.to_thread(self.diag.close)
                self.endpoint.close()
                if self.job_lease:self.job_lease.close()
                self.worker_lease.close()
                write_json(self.runtime/'capture_worker_status.json',{**self.info,'phase':'closed','heartbeat_ns':time.monotonic_ns()})
