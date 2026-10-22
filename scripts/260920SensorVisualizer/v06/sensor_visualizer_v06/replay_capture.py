"""Native frozen capture driven by trajectories or owned live snapshots."""
import asyncio
from bisect import bisect_right
from copy import deepcopy
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
from .control_ipc import request
from .internal_scheduling import group_boundary_yield

class ReplayCapture:
    def __init__(self,project,job):
        self.project=Path(project);self.job=job;self.spec=job['replay'];self.scene=None;self.pipeline=None
        self.session=Path(job['output_directory'])/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:8])
        self.session.mkdir(parents=True,exist_ok=False);self.diag=RunDiagnostics(job['output_directory'],job['diagnostics'],project)
        self.control=Path(self.spec['control_path']);self.status_path=Path(self.spec['status_path']);self.groups=0
        self.status={'state':'initializing','groups':0,'session':str(self.session),'mode':self.spec['mode']}
    def publish(self,**values):
        self.status.update(values);self.status['updated_ns']=time.monotonic_ns();write_json(self.status_path,self.status)
    def control_state(self):
        if not self.control.exists():return 'run'
        return json.loads(self.control.read_text()).get('action','run')
    async def source(self,group):
        mode=self.spec['mode'];hz=self.job['sample_hz']
        if mode=='offline':
            t=group/hz
            self.source_available_time=self.trajectory.duration
            if t>self.trajectory.duration+1e-8:return None
            return self.trajectory.sample(t)
        while self.control_state()!='stop':
            if self.control_state()=='pause':await asyncio.sleep(.1);continue
            if mode=='live_latest':
                response=await asyncio.to_thread(request,self.spec['socket'],{'action':'snapshot'})
                if response.get('phase')!='interactive_ready':raise RuntimeError('Interactive source unavailable')
                if time.monotonic_ns()-response['heartbeat_ns']>3_000_000_000:raise RuntimeError('Interactive snapshot stale')
                s=deepcopy(response['capture_snapshot'])
                if s['session_id']!=self.source_session:raise RuntimeError('Source session changed')
                if self.live_origin is None:self.live_origin=s['t_sim_s']
                s['t_sim_s']-=self.live_origin
                self.source_available_time=s['t_sim_s']
                if s['t_sim_s']>self.last_time+1e-8:return s
            else:
                path=Path(self.spec['trajectory']);meta=json.loads((path/'metadata.json').read_text());t=group/hz
                if meta.get('error'):raise RuntimeError('Trajectory source failed: '+meta['error'])
                if not meta.get('recording_complete'):
                    owner=await asyncio.to_thread(request,self.spec['socket'],{'action':'status'})
                    if owner.get('phase')!='interactive_ready' or time.monotonic_ns()-owner.get('heartbeat_ns',0)>3_000_000_000:
                        raise RuntimeError('Incomplete trajectory has lost its live owner')
                    self.source_available_time=owner['state']['t_sim_s']-meta.get('control_origin_s',0)
                else:self.source_available_time=meta.get('last_time_s')
                with (path/'states.jsonl').open(encoding='utf-8') as f:
                    f.seek(self.feed_offset)
                    while True:
                        # Read only through the next bracket, not the entire future feed.
                        if self.feed_rows and self.feed_rows[-1]['t_sim_s']>t+1e-8:break
                        start=f.tell();line=f.readline()
                        if not line or not line.endswith('\n'):f.seek(start);break
                        row=json.loads(line);revision=str(row['mount_revision'])
                        if revision not in meta.get('mount_revisions',{}):meta=json.loads((path/'metadata.json').read_text())
                        if revision not in meta.get('mount_revisions',{}):raise ValueError('Missing live mount revision snapshot')
                        row['mounts']=meta['mount_revisions'][revision]
                        self.feed_rows.append(row);self.feed_offset=f.tell()
                if self.feed_rows:
                    last=self.feed_rows[-1]['t_sim_s']
                    if last>t+1e-8 or (meta.get('recording_complete') and last>=t-1e-8):
                        i=max(0,bisect_right([r['t_sim_s'] for r in self.feed_rows],t)-1)
                        brackets=self.feed_rows[i:i+2]
                        out=Trajectory(brackets,meta).sample(t-brackets[0]['t_sim_s'])
                        out['t_sim_s']=t
                        # Keep only one preceding bracket; trajectory remains complete on disk.
                        self.feed_rows=self.feed_rows[i:]
                        return out
                    if meta.get('recording_complete'):return None
                    self.publish(state='waiting_trajectory',source_gap_sim_s=max(0,t-last))
            await asyncio.sleep(.05)
        return None
    async def run(self):
        if self.job.get('scheduling',{}).get('cpu_nice',0):os.nice(self.job['scheduling']['cpu_nice'])
        self.diag.start_resources();code=1;self.last_time=-1.;self.live_origin=None;self.feed_offset=0;self.feed_rows=[];self.source_available_time=None;self.skipped_grids=0
        try:
            if self.spec['mode']=='offline':
                self.trajectory=Trajectory.load(self.spec['trajectory']);metadata=self.trajectory.metadata
            else:
                source=await asyncio.to_thread(request,self.spec['socket'],{'action':'status'})
                if source.get('phase')!='interactive_ready':raise RuntimeError('Initialize interactive owner first')
                metadata=source['metadata'];self.source_session=source['session_id']
            expected=metadata.get('asset_manifest',{}).get('root_sha256')
            if expected and hashlib.sha256(Path(self.job['scene']).read_bytes()).hexdigest()!=expected:
                raise ValueError('Scene changed since trajectory/source initialization')
            self.scene=SceneStepper(self.project,self.job,self.diag);self.diag.attach_kit(self.scene.app)
            self.scene.on_phase=lambda name,values:self.publish(state=name,**values)
            await self.scene.initialize();self.scene.capture_id=uuid.uuid4().hex
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
                if state is None:break
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
                bundle['trajectory']={'snapshot_id':state['snapshot_id'],'source_session_id':state.get('session_id'),
                    'trajectory_time_s':state['t_sim_s'],'native_epoch_ns':self.scene.epoch_ns,'time_quantization_error_s':error,
                    'source_state_revision':state['state_revision'],'source_mount_revision':state['mount_revision'],'mode':self.spec['mode']}
                await self.pipeline.submit(slot,arrays,bundle);del arrays,bundle
                if self.spec['mode']=='live_latest':
                    if self.last_time>=0:self.skipped_grids+=max(0,round((state['t_sim_s']-self.last_time)*self.job['sample_hz'])-1)
                    try:
                        latest=await asyncio.to_thread(request,self.spec['socket'],{'action':'snapshot'})
                        self.source_available_time=latest.get('capture_snapshot',{}).get('t_sim_s')
                        if self.source_available_time is not None:self.source_available_time-=self.live_origin
                    except (OSError,EOFError,ValueError):self.source_available_time=None
                self.groups+=1;self.last_time=state['t_sim_s'];elapsed=time.monotonic()-started
                self.publish(state='capture_boundary',groups=self.groups,written=self.pipeline.written,
                    wall_groups_per_s=self.groups/max(elapsed,1e-9),wall_elapsed_s=elapsed,skipped_source_grids=self.skipped_grids,
                    source_lag_sim_s=max(0,self.source_available_time-self.last_time)
                        if self.spec['mode']!='offline' and self.source_available_time is not None else None)
                await group_boundary_yield(self.job.get('scheduling',{'cooperative_yield_ms':0}),self.spec.get('socket',''),self.diag,group)
            self.publish(state='draining');await self.scene.drivers.finish_generation();await self.pipeline.finish()
            self.publish(state='finished',groups=self.pipeline.written,written=self.pipeline.written,wall_s=time.monotonic()-started,stopped=self.control_state()=='stop');code=0
        except Exception:
            self.publish(state='failed',error=traceback.format_exc());traceback.print_exc()
            if self.pipeline and self.groups:
                try:await self.pipeline.finish()
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
            self.status['updated_ns']=time.monotonic_ns()
            write_json(self.session/'session.json',self.status);write_json(self.status_path,self.status)
        return code
