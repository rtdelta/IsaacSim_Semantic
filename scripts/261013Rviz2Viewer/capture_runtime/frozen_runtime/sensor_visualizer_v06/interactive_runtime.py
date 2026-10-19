"""Sensor-free interactive owner. Formal rendering is a separate process."""
import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import queue
import time
import uuid
from .contracts import load_job
from .scene import SceneStepper
from .control_ipc import ControlEndpoint
from .keyboard_control import KeyboardControl,KEYS
from .native_keyboard import NativeKeyboard
from .interaction_log import InteractionLog
from .trajectory import TrajectoryRecorder,Trajectory
from .diagnostics import RunDiagnostics
from .hot_path_metrics import HotPathMetrics
from contextlib import nullcontext

class InteractiveRuntime:
    def __init__(self,project,output=None,socket_path=None,job_path=None):
        self.project=Path(project);self.job=load_job(job_path,overrides={'mode':'interactive'})
        if output:self.job['output_directory']=str(output)
        self.output=Path(self.job['output_directory']);self.output.mkdir(parents=True,exist_ok=True)
        self.endpoint=ControlEndpoint(socket_path or self.output/'runtime/engine.sock')
        self.scene=None;self.task=None;self.recorder=None;self.subscription=None
        self.keyboard=KeyboardControl();self.native_keys=set();self.input=None;self.input_subscription=None
        self.closed=False;self.failed=False;self.error=None;self.playing=False;self.time_s=0.;self.revision=0;self.session_id=uuid.uuid4().hex;self.drains=set()
        self.last_tick=time.monotonic();self.last_publish=0.;self.state=None;self.capture_state=None
        self.transition='continuous';self.log=InteractionLog(self.output/'runtime/control_events.jsonl')
        self.lifecycle='initializing';self.busy=False;self.native=None;self.last_input_error=None;self.last_gap_log=0.;self.last_input_report=0.
        self.stats={'updates':0,'slow_updates':0,'max_owner_ms':0.,'owner_ms_samples':[],
            'frame_gap_max_ms':0.,'frame_gap_samples':[]};self.last_trajectory=None
        self.diag=None;self.hot=None
    def span(self,name):
        return self.hot.span(name) if self.hot else nullcontext()
    def event(self,name,**values):
        self.log.append({'event':name,'monotonic_ns':time.monotonic_ns(),'control_time_s':self.time_s,**values})
    async def initialize(self,open_scene=False):
        self.lifecycle='initializing';self.busy=True;self.failed=False;self.error=None;self.playing=False
        self.endpoint.publish({'phase':'initializing','motion_state':'initializing','heartbeat_ns':time.monotonic_ns()})
        if self.job['interactive']['diagnostics_enabled'] and self.diag is None:
            self.diag=RunDiagnostics(self.output,self.job['diagnostics'],self.project,role='interactive')
            self.diag.context(session_id=self.session_id,task='interactive',phase='initializing')
            self.diag.start_resources()
            self.hot=HotPathMetrics(self.diag,self.job['interactive']['trace_sample_every'])
        self.scene=SceneStepper(self.project,self.job,self.diag)
        try:
            await self.scene.initialize(open_scene=open_scene,sensor_products=False)
            if self.hot:self.scene.motion.performance=self.hot
            if self.diag:
                self.diag.detach_kit()
                self.diag.attach_kit(self.scene.app)
                self.diag.set_manifest(sensor_products=0,interactive_options=self.job['interactive'])
            self.scene.poses.simulation_time=lambda:self.time_s
            self.scene.poses.time_base='prescribed_control_simulation_seconds'
            self.metadata={'scene':self.scene.stage.GetRootLayer().realPath,'asset_manifest':self.scene.asset_manifest,
                'render':self.job['render'],'joint_names':list(self.scene.motion.controller.states),
                'root_frame':self.scene.config['root_frame'],'physics_hz':self.job['physics_hz'],'sample_hz':self.job['sample_hz'],
                'joint_definitions':self.scene.motion.config['joints'],'initial_mounts':self.scene.poses.snapshot(),
                'mount_revisions':{},'session_id':self.session_id,'native_preview_epoch_s':self.scene.native_time()}
            self.state=self._read_state();self.capture_state=deepcopy(self.state)
            self.keyboard.enabled=True;self.keyboard.clear();self.lifecycle='paused';self.busy=False
            self._subscribe_keyboard()
            self.last_tick=time.monotonic()
            self.subscription=self.scene.app.get_update_event_stream().create_subscription_to_pop(self._update,name='SV06 interactive owner')
            self.publish();self.event('interactive_ready',sensor_products=0)
        except Exception as exc:
            self.failed=True;self.error=str(exc);self.busy=False;self.lifecycle='failed';self.publish()
            raise
    def _subscribe_keyboard(self):
        import omni.appwindow,carb.input
        self.window=omni.appwindow.get_default_app_window()
        if self.window is None or self.window.get_keyboard() is None:return
        self.input=carb.input.acquire_input_interface();self.keyboard_device=self.window.get_keyboard()
        self.native=NativeKeyboard(self.keyboard,lambda:(self.window.is_focused(),
            self.window.get_input_blocking_state(carb.input.DeviceType.KEYBOARD),self.playing),self.event)
        self.native_keys=self.native.keys
        def on_key(event):
            try:return self.native.handle(event)
            except Exception as exc:
                message=str(exc);self.native.clear('input_error')
                if message!=self.last_input_error:self.event('native_input_error',error=message)
                self.last_input_error=message;return True
        self.input_subscription=self.input.subscribe_to_keyboard_events(self.keyboard_device,on_key)
    def _read_state(self):
        snap=self.scene.motion.snapshot(self.scene.native_time());names={j['name'] for j in self.scene.motion.config['joints']}
        if not hasattr(self,'cached_mounts') or self.cached_mount_revision!=self.scene.poses.revision:
            self.cached_mounts=self.scene.poses.snapshot();self.cached_mount_revision=self.scene.poses.revision
        return {'schema_version':1,'snapshot_id':uuid.uuid4().hex,'session_id':self.session_id,'t_sim_s':self.time_s,
            'native_preview_time_s':self.scene.native_time(),'state_revision':self.revision,'mount_revision':self.scene.poses.revision,
            'position_world_m':list(snap['root_position']),'quaternion_xyzw':list(snap['root_xyzw']),
            'joints_deg':{n:math.degrees(v) for n,v in zip(snap['names'],snap['positions']) if n in names},
            'mounts':self.cached_mounts,'transition_kind':self.transition,'base_control':snap['base_control']}
    def _commit(self,transition='continuous'):
        self.transition=transition;self.revision+=1;before=self.state;self.state=self._read_state()
        grid=math.floor((self.time_s+1e-9)*self.job['sample_hz'])/self.job['sample_hz']
        if self.capture_state is None or grid>self.capture_state['t_sim_s']+1e-9:
            if before and before['t_sim_s']<=grid:
                self.capture_state=Trajectory([before,self.state]).sample(grid-before['t_sim_s'])
                self.capture_state['t_sim_s']=grid
            else:self.capture_state=deepcopy(self.state);self.capture_state['t_sim_s']=grid
        if transition=='direct' and abs(grid-self.time_s)<1e-9:self.capture_state=deepcopy(self.state)
        if self.recorder:
            self.recorder.append(self.state,transition)
    def publish(self):
        if self.failed or self.lifecycle in ('exited','initializing','exiting'):
            self.endpoint.publish({'phase':'failed' if self.failed else self.lifecycle,'motion_state':self.lifecycle,
                'error':self.error,'playing':False,'keyboard_enabled':self.keyboard.enabled,'heartbeat_ns':time.monotonic_ns()});return
        if not self.scene or not self.state:return
        fast=self.job['interactive']['lightweight_publish']
        status={'phase':'interactive_ready','session_id':self.session_id,'heartbeat_ns':time.monotonic_ns(),
            'playing':self.playing,'keyboard_enabled':self.keyboard.enabled,'state':self.state,'capture_snapshot':self.capture_state,
            'motion_state':self.lifecycle,'input_status':{'native_reason':self.native.reason if self.native else 'unavailable',
                'native_events':self.native.events if self.native else 0,'native_last_event':self.native.last_event if self.native else None,
                'error':self.last_input_error,'last_apply_ms':self.keyboard.last_apply_ms,'pressed':sorted(self.keyboard.pressed()),
                'log_dropped':self.log.dropped,'log_error':self.log.error},
            'metadata':self.metadata,'recording':self.recorder is not None,'trajectory_path':str(self.recorder.directory) if self.recorder else self.last_trajectory,
            'joint_controls':{k:asdict(v) for k,v in self.scene.motion.controller.states.items()},
            'tilt_controls':{k:asdict(v) for k,v in self.scene.motion.base_controller.tilt.states.items()},
            'statistics':{k:list(v) if isinstance(v,list) else v for k,v in self.stats.items()} if fast else self.stats,
            'socket':str(self.endpoint.path),'rate_factor':self.job['max_real_time_factor']}
        # state/capture_state/metadata/mount generations are replaced, never edited after publication.
        if fast:self.endpoint.publish_owned(status)
        else:self.endpoint.publish(status)
    def command(self,m):
        if self.busy and m['action']!='close':raise ValueError('Controller lifecycle operation in progress')
        a=m['action'];p=m.get('payload',{});motion=self.scene.motion
        if a=='keys':self.keyboard.update(p.get('source','web'),p.get('keys',[]))
        elif a=='keyboard':
            self.keyboard.clear();self.native_keys.clear();self.keyboard.enabled=bool(p['enabled'])
            for k in ('linear_speed','angular_speed','joint_speed'):
                if k in p:
                    value=float(p[k])
                    if not math.isfinite(value) or not 0<value<=100:raise ValueError('Invalid keyboard speed')
                    setattr(self.keyboard,k,value)
        elif a=='play':self.playing=True;self.lifecycle='running';self.last_tick=time.monotonic()
        elif a=='pause':self.playing=False;self.lifecycle='paused';self.keyboard.clear();self.native_keys.clear()
        elif a=='motion':self.scene.apply_commands(p);self._commit('direct')
        elif a=='hold':motion.command('hold');motion.command_base('hold');self.keyboard.clear();self.native_keys.clear();self._commit()
        elif a=='mount':self.scene.poses.apply(p['id'],p['position_m'],p['rotation_deg']);self._commit('direct')
        elif a=='save_mounts':return {'path':str(self.scene.poses.save())}
        elif a=='reset_mounts':self.scene.poses.reset('web');self._commit('direct')
        elif a=='record_start':
            if self.recorder:raise ValueError('Already recording trajectory')
            directory=self.output/'trajectories'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
            self.recorder=TrajectoryRecorder(directory,self.metadata);self._commit('direct');self.publish();return {'path':str(directory)}
        elif a=='record_stop':
            if not self.recorder:raise ValueError('No active trajectory')
            recorder,self.recorder=self.recorder,None
            async def drain():
                try:
                    path=await asyncio.to_thread(recorder.close);self.last_trajectory=str(path)
                    self.endpoint.result(m,'applied',path=str(path));self.event('trajectory_closed',path=str(path));self.publish()
                except Exception as exc:self.endpoint.result(m,'failed',error=str(exc))
            task=asyncio.ensure_future(drain());self.drains.add(task);task.add_done_callback(self.drains.discard)
            return {'deferred':True}
        elif a in ('reset','stop'):
            if self.recorder or self.drains:raise ValueError('End trajectory and wait for its applied receipt before stopping or resetting')
            motion.reset();motion.tick(self.scene.native_time());self.scene.poses.reset('reset')
            self.keyboard.clear();self.native_keys.clear();self.playing=False;self.lifecycle='stopped' if a=='stop' else 'paused';self._commit('direct')
        elif a=='exit':
            if self.recorder or self.drains:raise ValueError('End trajectory and wait for its applied receipt before exiting')
            self.busy=True;self.lifecycle='exiting';self.playing=False;self.keyboard.clear();self.native_keys.clear();self.publish()
            async def exit_session():
                try:
                    self._unsubscribe_keyboard();await self.scene.close();self.lifecycle='exited'
                    self.endpoint.result(m,'applied');self.event('session_exited')
                except Exception as exc:self.failed=True;self.error=str(exc);self.lifecycle='failed';self.endpoint.result(m,'failed',error=str(exc))
                finally:self.busy=False;self.publish()
            asyncio.ensure_future(exit_session());return {'deferred':True}
        elif a=='reinitialize':
            if self.lifecycle not in ('exited','failed'):raise ValueError('Exit controller before reinitializing')
            self.busy=True
            async def reopen():
                try:
                    if self.scene and not self.scene.closed:await self.scene.close()
                    self.state=self.capture_state=None;self.time_s=0.;self.session_id=uuid.uuid4().hex
                    self.cached_mount_revision=-1;self.last_input_error=None
                    await self.initialize(open_scene=False);self.endpoint.result(m,'applied');self.event('session_reinitialized')
                except Exception as exc:self.busy=False;self.failed=True;self.error=str(exc);self.lifecycle='failed';self.endpoint.result(m,'failed',error=str(exc));self.publish()
            asyncio.ensure_future(reopen());return {'deferred':True}
        elif a=='close':asyncio.ensure_future(self.close());return {'deferred':True}
        else:raise ValueError('Unknown action: '+a)
        if a!='keys' or not getattr(self,'job',{}).get('interactive',{}).get('lightweight_publish',False):self.publish()
        return {'state_revision':self.revision}
    def _update(self,event):
        if self.closed:return
        if self.failed or self.lifecycle in ('exited','exiting','initializing'):
            for _ in range(16):
                try:m=self.endpoint.commands.get_nowait()
                except queue.Empty:break
                try:
                    if self.busy:raise ValueError('Controller lifecycle operation in progress')
                    if m['action'] not in ('close','reinitialize'):raise ValueError('Controller inactive; use Reinitialize Controller')
                    result=self.command(m)
                    if not result.get('deferred'):self.endpoint.result(m,'applied',**result)
                except Exception as exc:self.endpoint.result(m,'failed',error=str(exc))
            self.publish()
            return
        started=time.monotonic();wall_dt=max(0,started-self.last_tick);dt=min(.05,wall_dt);self.last_tick=started
        if self.hot:self.hot.begin_frame()
        gap_ms=wall_dt*1000;self.stats['frame_gap_max_ms']=max(self.stats['frame_gap_max_ms'],gap_ms)
        self.stats['frame_gap_samples'].append(gap_ms)
        if len(self.stats['frame_gap_samples'])>256:del self.stats['frame_gap_samples'][0]
        if gap_ms>100 and started-self.last_gap_log>1:self.event('main_update_gap',wall_dt_ms=gap_ms,playing=self.playing);self.last_gap_log=started
        try:
            self.scene.check_stage()
            if not self.scene.motion.ready:raise RuntimeError('Articulation handle invalid; close and reinitialize')
            if self.scene.timeline.is_playing():
                self.scene.timeline.pause();self.scene.timeline.commit();self.event('native_play_suppressed',use='web Play Simulation')
            if getattr(self,'window',None) and not self.window.is_focused():
                self.native_keys.clear();self.keyboard.sources.pop('native',None)
            elif getattr(self,'window',None):
                import carb.input
                if self.window.get_input_blocking_state(carb.input.DeviceType.KEYBOARD):
                    self.native_keys.clear();self.keyboard.sources.pop('native',None)
            command_start=time.monotonic();budget=self.job['interactive']['command_budget_ms']/1000
            for command_index in range(16):
                if command_index and time.monotonic()-command_start>=budget:break
                try:m=self.endpoint.commands.get_nowait()
                except queue.Empty:break
                try:
                    with self.span('control_command'):result=self.command(m)
                    if not result.get('deferred'):self.endpoint.result(m,'applied',**result)
                    if m['action']!='keys':self.event('control_dispatched' if result.get('deferred') else 'control_applied',
                        command_id=m['command_id'],action=m['action'],payload=m.get('payload',{}),
                        latency_ns=time.monotonic_ns()-m['accepted_ns'])
                except Exception as exc:self.endpoint.result(m,'failed',error=str(exc));self.event('control_failed',error=str(exc),action=m['action'])
            if self.playing:
                sim_dt=dt*self.job['max_real_time_factor'];motion=self.scene.motion
                with self.span('motion_integrate'):
                    moved=self.keyboard.step(motion,sim_dt);motion.controller.step(sim_dt);motion.base_controller.step(sim_dt)
                self.time_s+=sim_dt
                with self.span('native_pose_apply'):motion._apply_controlled_base(motion._command_angles())
                with self.span('state_commit'):self._commit()
                if moved and self.keyboard.input_revision!=self.keyboard.applied_revision:
                    self.keyboard.applied_revision=self.keyboard.input_revision
                    self.keyboard.last_apply_ms=(time.monotonic_ns()-self.keyboard.received_ns)/1e6
                    if self.keyboard.last_apply_ms>100 or started-self.last_input_report>1:
                        self.event('keyboard_pose_applied',input_revision=self.keyboard.input_revision,latency_ms=self.keyboard.last_apply_ms,
                            sources=list(self.keyboard.sources),wall_dt_s=wall_dt,sim_dt_s=sim_dt);self.last_input_report=started
            if started-self.last_publish>.1:
                with self.span('status_publish'):self.publish()
                self.last_publish=started
        except Exception as exc:
            self.failed=True;self.lifecycle='failed';self.error=str(exc);self.playing=False;self.keyboard.clear();self.event('owner_failed',error=str(exc))
            self.publish()
        elapsed=(time.monotonic()-started)*1000;self.stats['updates']+=1
        self.stats['max_owner_ms']=max(self.stats['max_owner_ms'],elapsed)
        if elapsed>50:self.stats['slow_updates']+=1;self.event('owner_slow',elapsed_ms=elapsed)
        self.stats['owner_ms_samples'].append(elapsed)
        if len(self.stats['owner_ms_samples'])>256:del self.stats['owner_ms_samples'][0]
        if self.hot:self.hot.finish_frame(frame_gap_ns=round(gap_ms*1e6),state_revision=self.revision,
            simulation_time_ns=round(self.time_s*1e9),command_queue_size=self.endpoint.commands.qsize(),session_id=self.session_id)
    def _unsubscribe_keyboard(self):
        if self.input_subscription is not None:
            self.input.unsubscribe_to_keyboard_events(self.keyboard_device,self.input_subscription);self.input_subscription=None
        if self.native:self.native.clear('exited')
    async def close(self):
        if self.closed:return
        self.closed=True;self.playing=False;self.keyboard.clear();self.subscription=None
        self._unsubscribe_keyboard()
        if self.recorder:
            r,self.recorder=self.recorder,None;await asyncio.to_thread(r.close)
        if self.drains:await asyncio.gather(*self.drains,return_exceptions=True)
        try:
            if self.scene:await self.scene.close()
        finally:
            self.event('closed')
            try:await asyncio.to_thread(self.log.close)
            finally:
                self.endpoint.close()
                if self.diag:
                    self.diag.detach_kit();await asyncio.to_thread(self.diag.close)
