"""Independent headless capture from a completed, task-owned state trajectory."""
import asyncio
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import traceback
import uuid
from .contracts import write_json
from .scene import SceneStepper
from .pipeline import RecordPipeline
from .diagnostics import RunDiagnostics
from .trajectory import Trajectory
from .offline_job import verify_replay_identity
from .frame_contract import CONTRACT
from .capture_plan import source_time_valid,verify_plan
from .scene_replay import place_state

class ReplayCapture:
    def __init__(self,project,job):
        self.project=Path(project);self.job=job;self.spec=job['replay'];self.scene=None;self.pipeline=None
        if self.spec['mode']!='offline':raise ValueError('Headless capture accepts only completed offline trajectories')
        self.session=Path(job['output_directory'])/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:8])
        self.session.mkdir(parents=True,exist_ok=False);self.diag=RunDiagnostics(job['output_directory'],job['diagnostics'],project)
        self.control=Path(self.spec['control_path']);self.status_path=Path(self.spec['status_path']);self.groups=0
        self.status={'state':'initializing','groups':0,'planned_groups':job['groups'],'session':str(self.session),'mode':self.spec['mode']}
        if job.get('capture_plan'):self.status['capture_plan']=job['capture_plan']
    def publish(self,**values):
        self.status.update(values);self.status['updated_ns']=time.monotonic_ns();write_json(self.status_path,self.status)
    def control_state(self):
        if not self.control.exists():return 'run'
        return json.loads(self.control.read_text()).get('action','run')
    async def source(self,group):
        elapsed=group/self.job['sample_hz']
        self.source_available_time=self.trajectory.duration
        if not source_time_valid(group,self.trajectory.duration,self.job['sample_hz']):return None
        return place_state(self.trajectory.sample(elapsed),self.spec.get('placement'))
    async def run(self):
        if self.job.get('scheduling',{}).get('cpu_nice',0):os.nice(self.job['scheduling']['cpu_nice'])
        self.diag.start_resources();code=1;self.last_time=-1.;self.live_origin=None;self.feed_offset=0;self.feed_rows=[];self.source_available_time=None;self.skipped_grids=0
        try:
            self.trajectory=Trajectory.load(self.spec['trajectory']);metadata=self.trajectory.metadata
            if self.job.get('capture_plan'):
                verify_plan(self.job['capture_plan'],self.trajectory.duration,self.job['groups'],self.job['sample_hz'],self.job['physics_hz'])
            expected=metadata.get('asset_manifest',{}).get('root_sha256')
            if self.spec.get('scene_policy','original')=='original' and expected and hashlib.sha256(Path(self.job['scene']).read_bytes()).hexdigest()!=expected:
                raise ValueError('Scene changed since trajectory/source initialization')
            self.scene=SceneStepper(self.project,self.job,self.diag);self.diag.attach_kit(self.scene.app)
            if self.spec.get('sensor_policy','recorded')=='recorded':
                from .scene_replay import replay_registry
                self.scene.recorded_registry=replay_registry(metadata,self.project)
            self.scene.source_states=self.trajectory.states
            self.scene.preflight=lambda scene:verify_replay_identity(metadata,scene)
            self.scene.on_phase=lambda name,values:self.publish(state=name,**values)
            await self.scene.initialize();self.scene.capture_id=uuid.uuid4().hex
            validation=verify_replay_identity(metadata,self.scene)
            replay_identity={'scene_policy':self.spec.get('scene_policy','original'),
                'sensor_policy':self.spec.get('sensor_policy','recorded'),
                'source_scene':metadata.get('scene'),'source_asset_manifest':metadata.get('asset_manifest'),
                'source_trajectory_file_hashes':metadata.get('source_file_hashes',metadata.get('file_hashes')),
                'target_scene':self.job['scene'],'target_asset_manifest':self.scene.asset_manifest,
                'placement':self.spec.get('placement'),'validation':validation}
            self.job['replay_identity']=replay_identity
            write_json(self.session/'replay_identity.json',replay_identity)
            self.scene.epoch_ns=round(self.scene.native_time()*1e9)
            self.scene.drivers.resource_policy=self.job['capture']['resource_policy']
            for name,value in [('job_spec.json',self.job),('sensor_registry.json',self.scene.registry),('render_profile.json',self.scene.render_actual),
                               ('asset_manifest.json',self.scene.asset_manifest),('trajectory_metadata.json',metadata)]:write_json(self.session/name,value)
            self.pipeline=RecordPipeline(self.project,self.session,self.job,self.scene.registry,self.scene.render_actual,self.scene.capture_id,self.diag)
            await self.pipeline.start();started=time.monotonic()
            for group in range(self.job['groups']):
                while self.control_state()=='pause':self.publish(state='paused');self.pipeline.poll();await asyncio.sleep(.1)
                if self.control_state()=='stop':break
                state=await self.source(group)
                if state is None:
                    if self.job.get('capture_plan'):raise RuntimeError('Trajectory source exhausted before the capture plan completed')
                    break
                self.publish(state='waiting_slot',source_time_s=state['t_sim_s'])
                slot=await self.pipeline.reserve(group,lambda:self.control_state()=='stop')
                if slot is None:break
                self.scene.drivers.set_capture_active(True)
                await self.scene.advance_clock(state['t_sim_s'])
                self.scene.apply_snapshot(state)
                stamp=round(self.scene.native_time()*1e9)
                # Formal source time remains native, with explicit trajectory mapping.
                error=(stamp-self.scene.epoch_ns)/1e9-state['t_sim_s']
                if abs(error)>.5/self.job['physics_hz']+1e-6:raise RuntimeError('Trajectory/native time mapping failed')
                arrays,bundle=await self.scene.capture(group,stamp)
                readback=self.scene.motion.snapshot(self.scene.native_time())
                bundle['frame_contract']=dict(CONTRACT,swing_zero_mapping=self.scene.motion.config['swing_zero_mapping'],swing_zero_readback=readback['swing_zero_readback'])
                bundle['trajectory']={'swing_zero_readback':readback['swing_zero_readback'],'snapshot_id':state['snapshot_id'],'source_session_id':state.get('session_id'),
                    'trajectory_time_s':state['t_sim_s'],'native_epoch_ns':self.scene.epoch_ns,'time_quantization_error_s':error,
                    'source_state_revision':state['state_revision'],'source_mount_revision':state['mount_revision'],'mode':self.spec['mode']}
                bundle['trajectory'].update(scene_policy=self.spec.get('scene_policy','original'),placement=self.spec.get('placement'))
                await self.pipeline.submit(slot,arrays,bundle);del arrays,bundle
                self.groups+=1;self.last_time=state['t_sim_s'];elapsed=time.monotonic()-started
                self.publish(state='capture_boundary',groups=self.groups,written=self.pipeline.written,
                    wall_groups_per_s=self.groups/max(elapsed,1e-9),wall_elapsed_s=elapsed,skipped_source_grids=self.skipped_grids,
                    source_lag_sim_s=max(0,self.source_available_time-self.last_time)
                        if self.spec['mode']!='offline' and self.source_available_time is not None else None)
            complete=self.groups==self.job['groups']
            stopped=not complete and self.control_state()=='stop'
            if self.job.get('capture_plan') and not complete and not stopped:raise RuntimeError('Capture plan ended without completion or user stop')
            self.publish(state='draining',capture_phase_finished=True,capture_complete=complete)
            await self.scene.drivers.finish_generation();await self.pipeline.finish()
            if self.pipeline.written!=self.groups:raise RuntimeError('Written group count differs from captured groups')
            self.publish(record_drain_complete=True)
            self.publish(state='finished',groups=self.groups,written=self.pipeline.written,wall_s=time.monotonic()-started,
                         completion_reason='stopped_by_user' if stopped else 'completed_plan',stopped=stopped);code=0
        except Exception:
            self.publish(state='failed',completion_reason='failed',error=traceback.format_exc());traceback.print_exc()
            if self.pipeline and self.groups:
                try:
                    await self.pipeline.finish()
                    self.publish(written=self.pipeline.written,record_drain_complete=self.pipeline.written==self.groups)
                except Exception as exc:self.publish(drain_error=str(exc))
        finally:
            # Cleanup announces its own phase; preserve the terminal result.
            terminal=dict(self.status)
            if self.scene:self.scene.on_phase=lambda *args,**kwargs:None
            if self.pipeline:
                try:await self.pipeline.close()
                except Exception as exc:self.publish(cleanup_error=str(exc));code=1
            if self.scene:
                try:await self.scene.close()
                except Exception as exc:self.publish(scene_cleanup_error=str(exc));code=1
            self.diag.detach_kit();await asyncio.to_thread(self.diag.close)
            self.status.update(terminal)
            self.status['state']='failed' if code else 'finished'
            if code:self.status['completion_reason']='failed'
            self.status['resources_cleaned']=code==0
            self.status['updated_ns']=time.monotonic_ns()
            write_json(self.session/'session.json',self.status);write_json(self.status_path,self.status)
        return code
