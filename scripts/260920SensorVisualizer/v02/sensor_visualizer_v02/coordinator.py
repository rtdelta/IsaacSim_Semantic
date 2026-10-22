"""One owner for scene changes; immutable groups handed to parallel recording."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time
import traceback
import uuid
from .contracts import SampleClock, write_json
from .pipeline import RecordPipeline
from .telemetry import Telemetry


class CaptureRunner:
    def __init__(self,project,job,scene=None):
        self.project,self.job,self.scene=Path(project),job,scene
        self.owns_scene=scene is None
        self.paused=False; self.stop_requested=False; self.phase='idle'; self.groups=0
        self.actions=[]; self.pipeline=None; self.session=None; self.error=None; self.on_update=None

    def stop(self): self.stop_requested=True; self.paused=False
    def pause(self): self.paused=True
    def resume(self): self.paused=False
    def enqueue(self,description,action): self.actions.append((description,action))

    async def run(self):
        from .scene import SceneStepper
        token=uuid.uuid4().hex[:10]
        self.session=Path(self.job['output_directory'])/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+token)
        self.session.mkdir(parents=True,exist_ok=False)
        status={'schema_version':2,'state':'initializing','job_id':token,'started_utc':datetime.now(timezone.utc).isoformat(),
                'requested_groups':self.job['groups'],'complete_groups':0,'mode':self.job['mode']}
        write_json(self.session/'job_spec.json',self.job); write_json(self.session/'session.json',status)
        monitor=Telemetry(self.session/'performance')
        active_start=None
        try:
            if self.scene is None: self.scene=SceneStepper(self.project,self.job)
            if self.scene.drivers is None:
                self.phase='initializing'; await self.scene.initialize(open_scene=self.owns_scene)
            self.scene.job=self.job
            self.scene.apply_commands(self.job['motion'])
            self.scene.epoch_ns=round(self.scene.native_time()*1e9)
            clock=SampleClock(self.job['sample_hz'],self.scene.epoch_ns)
            write_json(self.session/'sensor_registry.json',self.scene.registry)
            write_json(self.session/'render_profile.json',self.scene.render_actual)
            write_json(self.session/'asset_manifest.json',self.scene.asset_manifest)
            write_json(self.session/'mount_poses_at_start.json',self.scene.poses.snapshot())
            status.update(state='starting_writer',epoch_ns=clock.epoch_ns)
            write_json(self.session/'session.json',status)
            self.pipeline=RecordPipeline(self.project,self.session,self.job,self.scene.registry,self.scene.render_actual,token)
            await self.pipeline.start(); monitor.pids['record_worker']=self.pipeline.process.pid
            active_start=time.monotonic(); last_advance=None
            status['state']='capturing'; write_json(self.session/'session.json',status)
            for group in range(self.job['groups']):
                while not self.stop_requested:
                    self.pipeline.poll(); self._actions(monitor)
                    remaining=0 if last_advance is None or self.job['mode']=='offline' else (
                        last_advance+1/self.job['sample_hz']/self.job['max_real_time_factor']-time.monotonic())
                    if not self.paused and remaining<=0: break
                    self.phase=monitor.phase='paused' if self.paused else 'pacing'
                    if self.on_update: self.on_update(self)
                    await asyncio.sleep(.05)
                if self.stop_requested: break
                self._actions(monitor)
                for event in self.job['events']:
                    if event['group']==group:
                        self.scene.apply_commands(event.get('motion',{})); monitor.event('command',group_id=group,command=event)
                monitor.group=group
                t=time.perf_counter(); slot=await self.pipeline.reserve(group)
                monitor.measure('buffer_wait',time.perf_counter()-t,group_id=group)
                self.phase=monitor.phase='advancing'; t=time.perf_counter()
                last_advance=time.monotonic()
                await self.scene.advance(group); monitor.measure('advance',time.perf_counter()-t,group_id=group)
                self.phase=monitor.phase='frozen_capture'; t=time.perf_counter()
                arrays,bundle=await self.scene.capture(group,clock.stamp(group))
                monitor.measure('render_and_readback',time.perf_counter()-t,group_id=group)
                for name,duration in self.scene.last_capture_timings.items():
                    monitor.measure(name,duration,group_id=group)
                t=time.perf_counter(); self.pipeline.submit(slot,arrays,bundle)
                monitor.measure('copy_and_submit',time.perf_counter()-t,group_id=group)
                del arrays,bundle
                self.groups=group+1
                if self.on_update: self.on_update(self)
            self.phase=monitor.phase='draining'; await self.pipeline.finish()
            self.groups=self.pipeline.written
            elapsed=time.monotonic()-active_start
            status.update(state='finished',complete_groups=self.groups,wall_capture_s=elapsed,
                          groups_per_wall_s=self.groups/elapsed if elapsed else None,
                          stopped_early=self.stop_requested,finished_utc=datetime.now(timezone.utc).isoformat())
        except Exception:
            self.error=traceback.format_exc(); self.phase='failed'
            if self.pipeline and self.groups:
                try:
                    await self.pipeline.finish()
                    status['partial_recording_closed']=True
                except Exception as exc:
                    status['partial_recording_error']=str(exc)
            status.update(state='failed',error=self.error,submitted_groups=self.groups,
                          complete_groups=self.pipeline.written if self.pipeline else 0)
            monitor.event('failure',error=self.error)
            print('[SV02 ERROR] '+self.error,flush=True)
        finally:
            if self.pipeline:
                try: await self.pipeline.close()
                except Exception as exc: status.update(cleanup_error=str(exc))
            if self.scene and self.owns_scene:
                try: await self.scene.close()
                except Exception as exc: status.update(scene_cleanup_error=str(exc))
            monitor.close(); write_json(self.session/'session.json',status)
            self.phase=status['state']
            if self.on_update: self.on_update(self)
            print('[SV02 RESULT] '+str(self.session),flush=True)
        return status

    def _actions(self,monitor):
        while self.actions:
            description, action=self.actions.pop(0)
            try:
                action(); monitor.event('control',description=description,next_group=self.groups)
            except Exception as exc:
                monitor.event('control_rejected',description=description,error=str(exc))
                print('[SV02 CONTROL REJECTED] '+str(exc),flush=True)
