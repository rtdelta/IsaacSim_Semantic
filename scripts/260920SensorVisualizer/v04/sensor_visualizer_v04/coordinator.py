"""One owner for scene changes; immutable groups handed to parallel recording."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time
import traceback
import uuid
from .contracts import SampleClock, write_json
from .pipeline import RecordPipeline
from .diagnostics import RunDiagnostics, CaptureTelemetry


class CaptureRunner:
    def __init__(self,project,job,scene=None,diagnostics=None):
        self.project,self.job,self.scene=Path(project),job,scene
        self.owns_scene=scene is None
        self.owns_diagnostics=diagnostics is None
        self.diag=diagnostics or RunDiagnostics(job['output_directory'],job['diagnostics'],project)
        self.diag.start_resources()
        self.pending=[]; self.last_ui=0; self.capture_id=None; self.controls=[]
        self.paused=False; self.stop_requested=False; self.phase='idle'; self.groups=0
        self.actions=[]; self.pipeline=None; self.session=None; self.error=None; self.on_update=None

    def control(self,name):
        control_id=uuid.uuid4().hex;self.controls.append((name,control_id,time.monotonic_ns()))
        self.diag.event('control_requested',critical=True,control=name,control_id=control_id)
        self.diag.event('control_accepted',critical=True,control=name,control_id=control_id,boundary='next safe group boundary')
    def stop(self): self.control('stop'); self.stop_requested=True; self.paused=False
    def pause(self): self.control('pause'); self.paused=True
    def resume(self): self.control('resume'); self.paused=False
    def enqueue(self,description,action):
        self.control(description); self.actions.append((description,action))
    def set_phase(self,name,values=None):
        changed=self.phase!=name; self.phase=name
        self.pending=(values or {}).get('pending',[])
        self.diag.context(phase=name)
        if changed: self.diag.event('phase_changed',critical=True)
        applied={'paused':'pause','draining':'stop'}.get(name)
        for control,cid,started in list(self.controls):
            if control==applied or control=='resume' and name not in ('paused','waiting_slot'):
                self.diag.event('control_applied',critical=True,control=control,control_id=cid,latency_ns=time.monotonic_ns()-started)
                self.controls.remove((control,cid,started))
        now=time.monotonic()
        if self.on_update and (changed or now-self.last_ui>.2):
            self.on_update(self); self.last_ui=now

    async def run(self):
        from .scene import SceneStepper
        token=uuid.uuid4().hex[:10]; self.capture_id=token
        self.diag.context(capture_id=token,group_id=None)
        self.session=Path(self.job['output_directory'])/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+token)
        self.session.mkdir(parents=True,exist_ok=False)
        status={'schema_version':2,'state':'initializing','job_id':token,'started_utc':datetime.now(timezone.utc).isoformat(),
                'requested_groups':self.job['groups'],'complete_groups':0,'mode':self.job['mode']}
        write_json(self.session/'job_spec.json',self.job); write_json(self.session/'session.json',status)
        write_json(self.session/'diagnostics_ref.json',{'run_id':self.diag.run_id,'directory':str(self.diag.directory),'capture_id':token})
        monitor=CaptureTelemetry(self.session/'performance',self.diag)
        active_start=None
        try:
            if self.scene is None:
                self.scene=SceneStepper(self.project,self.job,self.diag)
                self.diag.attach_kit(self.scene.app)
            self.scene.on_phase=self.set_phase; self.scene.capture_id=token
            if self.scene.drivers is None:
                self.set_phase('initializing')
                with self.diag.span('initialize'): await self.scene.initialize(open_scene=self.owns_scene)
            self.scene.job=self.job
            if hasattr(self.scene.drivers,'backend'):
                if self.scene.drivers.backend!=self.job['capture']['backend']:
                    raise ValueError('Capture backend changed; reinitialize the stage')
                self.scene.drivers.resource_policy=self.job['capture']['resource_policy']
            self.scene.apply_commands(self.job['motion'])
            self.scene.epoch_ns=round(self.scene.native_time()*1e9)
            clock=SampleClock(self.job['sample_hz'],self.scene.epoch_ns)
            write_json(self.session/'sensor_registry.json',self.scene.registry)
            write_json(self.session/'render_profile.json',self.scene.render_actual)
            write_json(self.session/'asset_manifest.json',self.scene.asset_manifest)
            write_json(self.session/'mount_poses_at_start.json',self.scene.poses.snapshot())
            status.update(state='starting_writer',epoch_ns=clock.epoch_ns)
            write_json(self.session/'session.json',status)
            self.pipeline=RecordPipeline(self.project,self.session,self.job,self.scene.registry,self.scene.render_actual,token,self.diag)
            await self.pipeline.start(); monitor.pids['record_worker']=self.pipeline.process.pid
            active_start=time.monotonic(); last_advance=None
            status['state']='capturing'; write_json(self.session/'session.json',status)
            for group in range(self.job['groups']):
                self.diag.context(group_id=group,request_id=None,attempt_id=None)
                if hasattr(self.scene.drivers,'set_capture_active'):
                    self.scene.drivers.set_capture_active(not self.paused and not self.stop_requested)
                self.scene.check_stage(); self.scene.drivers.suspend_all('group_boundary')
                while not self.stop_requested:
                    self.pipeline.poll(); self._actions(monitor)
                    remaining=0 if last_advance is None or self.job['mode']=='offline' else (
                        last_advance+1/self.job['sample_hz']/self.job['max_real_time_factor']-time.monotonic())
                    if not self.paused and remaining<=0: break
                    if getattr(self.scene.drivers,'generation_open',False):
                        await self.scene.drivers.finish_generation()
                    self.set_phase('paused' if self.paused else 'pacing')
                    await asyncio.sleep(.05)
                if self.stop_requested: break
                if hasattr(self.scene.drivers,'set_capture_active'):self.scene.drivers.set_capture_active(True)
                self._actions(monitor)
                for event in self.job['events']:
                    if event['group']==group:
                        self.scene.apply_commands(event.get('motion',{})); monitor.event('command',group_id=group,command=event)
                monitor.group=group
                self.set_phase('waiting_slot')
                t=time.perf_counter(); slot=await self.pipeline.reserve(group,lambda:self.stop_requested or self.paused)
                if slot is None:
                    if self.stop_requested: break
                    while self.paused and not self.stop_requested:
                        self.set_phase('paused'); self.pipeline.poll(); self._actions(monitor); await asyncio.sleep(.05)
                    if self.stop_requested: break
                    slot=await self.pipeline.reserve(group,lambda:self.stop_requested)
                    if slot is None: break
                monitor.measure('buffer_wait',time.perf_counter()-t,group_id=group)
                self.set_phase('advancing'); t=time.perf_counter()
                last_advance=time.monotonic()
                await self.scene.advance(group); monitor.measure('advance',time.perf_counter()-t,group_id=group)
                self.set_phase('frozen_capture'); t=time.perf_counter()
                arrays,bundle=await self.scene.capture(group,clock.stamp(group))
                monitor.measure('render_and_readback',time.perf_counter()-t,group_id=group)
                for name,duration in self.scene.last_capture_timings.items():
                    monitor.measure(name,duration,group_id=group)
                self.set_phase('packing')
                t=time.perf_counter(); await self.pipeline.submit(slot,arrays,bundle)
                monitor.measure('copy_and_submit',time.perf_counter()-t,group_id=group)
                del arrays,bundle
                self.groups=group+1
                if self.on_update: self.on_update(self)
            self.set_phase('draining'); self.scene.drivers.suspend_all('drain')
            if hasattr(self.scene.drivers,'finish_generation'):await self.scene.drivers.finish_generation()
            if self.stop_requested: self.diag.event('control_applied',critical=True,control='stop')
            await self.pipeline.finish()
            self.groups=self.pipeline.written
            elapsed=time.monotonic()-active_start
            status.update(state='finished',complete_groups=self.groups,wall_capture_s=elapsed,
                          groups_per_wall_s=self.groups/elapsed if elapsed else None,
                          stopped_early=self.stop_requested,finished_utc=datetime.now(timezone.utc).isoformat())
        except Exception:
            self.error=traceback.format_exc(); self.set_phase('failed')
            if self.scene: self.scene.capture_failed=True
            if self.pipeline and self.groups:
                try:
                    await self.pipeline.finish()
                    status['partial_recording_closed']=True
                except Exception as exc:
                    status['partial_recording_error']=str(exc)
            status.update(state='failed',error=self.error,submitted_groups=self.groups,
                          complete_groups=self.pipeline.written if self.pipeline else 0)
            monitor.event('failure',error=self.error)
            print('[SV04 ERROR] '+self.error,flush=True)
        finally:
            if self.pipeline:
                try: await self.pipeline.close()
                except Exception as exc: status.update(cleanup_error=str(exc))
            if self.scene and self.scene.drivers:
                try: self.scene.drivers.suspend_all('capture_finished')
                except Exception as exc: self.diag.warning('resource_handle_invalid',str(exc))
            if self.scene and self.owns_scene:
                try: await self.scene.close()
                except Exception as exc: status.update(scene_cleanup_error=str(exc))
            monitor.close(); write_json(self.session/'session.json',status)
            self.set_phase(status['state'])
            self.diag.event('capture_finished',critical=True,state=status['state'],groups=self.groups)
            if self.owns_diagnostics:
                self.diag.detach_kit()
                await asyncio.to_thread(self.diag.close)
            if self.on_update: self.on_update(self)
            print('[SV04 RESULT] '+str(self.session),flush=True)
        return status

    def _actions(self,monitor):
        while self.actions:
            description, action=self.actions.pop(0)
            try:
                action(); monitor.event('control_applied',description=description,next_group=self.groups)
            except Exception as exc:
                monitor.event('control_rejected',description=description,error=str(exc))
                print('[SV04 CONTROL REJECTED] '+str(exc),flush=True)
