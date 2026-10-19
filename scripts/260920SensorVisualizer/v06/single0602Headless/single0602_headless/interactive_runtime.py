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
from .frame_contract import validate_metadata
from .diagnostics import RunDiagnostics
from .hot_path_metrics import HotPathMetrics
from .interaction_clock import NativeStepClock,NATIVE_TIME_BASE
from . import __version__
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
            'frame_gap_max_ms':0.,'frame_gap_samples':[],'physics_steps':0,'max_step_ms':0.};self.last_trajectory=None
        self.diag=None;self.hot=None
        self.clock=NativeStepClock();self.timeline_subscription=None;self.physics_callback=None
        self.timeline_state='paused';self.binding_pending=False;self.binding_deadline=0.
        self.trajectory_phase='idle';self.trajectory_error=None
        self.run_wall_start=None;self.run_native_start=None;self.play_wall_s=0.;self.play_native_s=0.
        self.keyboard.notify=self.event
    def span(self,name):
        return self.hot.span(name) if self.hot else nullcontext()
    def event(self,name,**values):
        row={'event':name,'monotonic_ns':time.monotonic_ns(),'control_time_s':self.time_s,**values}
        self.log.append(row)
        if self.recorder:
            try:self.recorder.append_event(row)
            except Exception as exc:
                self._finish_recording('writer_failed',error=exc)
                self.log.append(dict(row,event='trajectory_write_failed',error=str(exc)))
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
            self.clock.bind(self.scene.native_time());self.time_s=0.
            self.scene.poses.time_base=NATIVE_TIME_BASE
            self.metadata={'implementation_version':__version__,'scene':self.scene.stage.GetRootLayer().realPath,'asset_manifest':self.scene.asset_manifest,
                'render':self.job['render'],'joint_names':list(self.scene.motion.controller.states),
                'root_frame':self.scene.config['root_frame'],'physics_hz':self.job['physics_hz'],'sample_hz':self.job['sample_hz'],
                'joint_definitions':self.scene.motion.config['joints'],'initial_mounts':self.scene.poses.snapshot(),
                'mount_revisions':{},'session_id':self.session_id,'native_preview_epoch_s':self.scene.native_time()}
            self.metadata.update(self.scene.motion.frame_metadata())
            self.metadata['robot_binding']=self.scene.config['robot_binding']
            self.metadata.update(time_base=NATIVE_TIME_BASE,time_basis_version=2,
                native_clock_origin_s=self.clock.origin,interaction_target_rate=1.,
                motion_model='discrete_positions_zero_physical_velocity')
            validate_metadata(self.metadata)
            self.state=self._read_state();self.capture_state=deepcopy(self.state)
            self.keyboard.enabled=False;self.keyboard.clear('initialized');self.lifecycle='paused';self.busy=False
            self.timeline_state='paused';self.binding_pending=False
            self._subscribe_keyboard()
            self._subscribe_simulation()
            self.last_tick=time.monotonic()
            self.subscription=self.scene.app.get_update_event_stream().create_subscription_to_pop(self._update,name='S0602 interactive owner')
            self.publish();self.event('interactive_ready',sensor_products=0)
        except Exception as exc:
            self.failed=True;self.error=str(exc);self.busy=False;self.lifecycle='failed';self.publish()
            raise
    def _subscribe_keyboard(self):
        import omni.appwindow,carb.input
        self.window=omni.appwindow.get_default_app_window()
        if self.window is None or self.window.get_keyboard() is None:return
        self.input=carb.input.acquire_input_interface();self.keyboard_device=self.window.get_keyboard()
        self.native=NativeKeyboard(self.keyboard,self._native_context,self._native_event,self.apply_keyboard)
        def on_key(event):
            try:return self.native.handle(event)
            except Exception as exc:
                message=str(exc);self.native.clear('input_error')
                if message!=self.last_input_error:self.event('native_input_error',error=message)
                self.last_input_error=message;return True
        self.input_subscription=self.input.subscribe_to_keyboard_events(self.keyboard_device,on_key)
    def _native_context(self):
        import carb.input
        import omni.kit.viewport.utility
        viewport=omni.kit.viewport.utility.get_active_viewport_window()
        return {'application_focused': bool(self.window and self.window.is_focused()),
                'viewport_focused': bool(viewport and getattr(viewport,'focused',False)),
                'input_blocked': bool(self.window and self.window.get_input_blocking_state(carb.input.DeviceType.KEYBOARD)),
                'playing': self.playing and not self.binding_pending}
    def _hold_actual(self):
        self._require_binding()
        self.scene.motion.synchronize_control_from_actual()
    def _native_event(self,name,**values):
        if name=='native_key' and values.get('kind')=='KEY_PRESS' and values.get('outcome')=='accepted':
            self._hold_actual()
        self.event(name,**values)
    def apply_keyboard(self,payload,source='web'):
        self.keyboard.configure(payload)
        if not self.binding_pending and self.timeline_state!='stopped' and self.scene.motion.ready:
            self._hold_actual();self._commit()
        result={'input_epoch':self.keyboard.input_epoch,'keyboard':self.keyboard.status(),'state_revision':self.revision}
        self.event('keyboard_mode_applied',source=source,**result)
        if source=='native_f8':
            self.endpoint.result({'command_id':uuid.uuid4().hex,'action':'keyboard','accepted_ns':time.monotonic_ns()},'applied',**result)
        self.publish()
        return result
    def _require_binding(self):
        if self.binding_pending or self.timeline_state=='stopped' or not self.scene.motion.ready:
            raise ValueError('Play Simulation and wait for articulation binding before controlling or recording')
    def _subscribe_simulation(self):
        from isaacsim.core.simulation_manager import SimulationEvent
        self.timeline_subscription=self.scene.timeline.get_timeline_event_stream().create_subscription_to_pop(
            self._timeline_event,name='S0602 native lifecycle')
        self.physics_callback=self.scene.manager.register_callback(
            self._physics_post,SimulationEvent.PHYSICS_POST_STEP,order=1000)
    def _unsubscribe_simulation(self):
        self.timeline_subscription=None
        if self.physics_callback is not None:
            self.scene.manager.deregister_callback(self.physics_callback);self.physics_callback=None
    def _timeline_event(self,event):
        import omni.timeline
        if event.type in (int(omni.timeline.TimelineEventType.PLAY),int(omni.timeline.TimelineEventType.PAUSE),
                          int(omni.timeline.TimelineEventType.STOP)):
            try:self._sync_timeline()
            except Exception as exc:self._fail(exc)
    def _stop_rate_measurement(self):
        if self.run_wall_start is not None:
            self.play_wall_s+=time.monotonic()-self.run_wall_start
            self.play_native_s+=max(0.,self.clock.last-self.run_native_start)
            self.run_wall_start=self.run_native_start=None
    def _rate_statistics(self):
        wall=self.play_wall_s;native=self.play_native_s
        if self.run_wall_start is not None:
            wall+=time.monotonic()-self.run_wall_start
            native+=max(0.,self.clock.last-self.run_native_start)
        return {'target':1.,'actual':native/wall if wall>0 else None,'playing_wall_s':wall,'playing_native_s':native}
    def _sync_timeline(self):
        timeline=self.scene.timeline
        state='playing' if timeline.is_playing() else 'stopped' if timeline.is_stopped() else 'paused'
        if state==self.timeline_state:return
        previous=self.timeline_state;self.timeline_state=state
        self.playing=state=='playing'
        if state!='playing':self._stop_rate_measurement()
        if state=='stopped':
            self.keyboard.clear('native_stop');self.native_keys.clear();self.scene.motion.cancel_commands()
            self.binding_pending=True;self.lifecycle='stopped'
            self.event('native_stop',last_valid_native_time_s=self.clock.last)
            self._finish_recording('native_stop')
        elif state=='paused':
            self.keyboard.clear('native_pause');self.lifecycle='paused'
        else:
            self.keyboard.clear('native_play')
            if previous=='stopped':
                self.binding_pending=True;self.binding_deadline=time.monotonic()+30
            self.lifecycle='binding' if self.binding_pending else 'running'
            if not self.binding_pending:
                self.run_wall_start=time.monotonic();self.run_native_start=self.clock.last
        self.event('timeline_'+state,previous=previous)
        self.publish()
    def _try_rebind(self):
        if not self.binding_pending or self.timeline_state=='stopped':return False
        native=self.scene.native_time()
        if not self.scene.motion.rebind_from_actual(native):return False
        self.clock.bind(native);self.time_s=0.;self.capture_state=None
        self.keyboard.horizontal.reset();self.binding_pending=False
        self.metadata=dict(self.metadata,native_clock_origin_s=native,
            native_preview_epoch_s=native,initial_mounts=self.scene.poses.snapshot(),
            **self.scene.motion.frame_metadata())
        self._commit('direct');self.lifecycle='running' if self.playing else 'paused'
        if self.playing:
            self.run_wall_start=time.monotonic();self.run_native_start=native
        self.event('articulation_rebound',native_epoch=self.clock.generation);self.publish()
        return True
    def _finish_recording(self,reason,message=None,error=None):
        if not self.recorder:return False
        recorder,self.recorder=self.recorder,None
        recorder.final_metadata=dict(end_reason=reason,last_valid_native_time_s=self.clock.last,
            last_valid_seq=recorder.count-1,interaction_rate=self._rate_statistics())
        if error:recorder.error=recorder.error or str(error)
        self.last_trajectory=str(recorder.directory)
        self.trajectory_phase='draining';self.trajectory_error=None
        async def drain():
            try:
                path=await asyncio.to_thread(recorder.close);self.last_trajectory=str(path)
                self.trajectory_phase='complete'
                if message:self.endpoint.result(message,'applied',path=str(path),recording_complete=True)
                self.event('trajectory_closed',path=str(path),reason=reason)
            except Exception as exc:
                self.last_trajectory=str(recorder.directory);self.trajectory_phase='failed';self.trajectory_error=str(exc)
                if message:self.endpoint.result(message,'failed',error=str(exc))
                self.event('trajectory_close_failed',error=str(exc),reason=reason)
            finally:
                self.drains.discard(asyncio.current_task());self.publish()
        task=asyncio.ensure_future(drain());self.drains.add(task)
        return True
    def _fail(self,exc):
        if self.failed:return
        self.failed=True;self.lifecycle='failed';self.error=str(exc);self.playing=False
        self._stop_rate_measurement();self.keyboard.clear('owner_failed')
        self.scene.motion.cancel_commands()
        self._finish_recording('owner_failed',error=exc)
        self.event('owner_failed',error=str(exc));self.publish()
    def _physics_post(self,step_dt,context):
        if self.closed or self.failed or self.busy or self.lifecycle in ('exited','exiting','initializing'):return
        started=time.monotonic()
        try:
            self._sync_timeline()
            if not self.playing:return
            self.scene.check_stage()
            if self.binding_pending:
                self._try_rebind();return
            self._require_binding()
            if self.native:self.native.poll_focus()
            dt=self.clock.advance(self.scene.native_time(),step_dt)
            if not dt:return
            motion=self.scene.motion
            with self.span('motion_integrate'):
                moved=self.keyboard.step(motion,dt);motion.controller.step(dt);motion.base_controller.step(dt)
            self.time_s=self.clock.elapsed
            self.stats['physics_steps']+=1
            with self.span('native_pose_apply'):motion._apply_controlled_base(motion._command_angles())
            with self.span('state_commit'):self._commit()
            if moved and self.keyboard.input_revision!=self.keyboard.applied_revision:
                self.keyboard.applied_revision=self.keyboard.input_revision
                self.keyboard.last_apply_ms=(time.monotonic_ns()-self.keyboard.received_ns)/1e6
                now=time.monotonic()
                if self.keyboard.last_apply_ms>100 or now-self.last_input_report>1:
                    self.event('keyboard_pose_applied',input_revision=self.keyboard.input_revision,
                        latency_ms=self.keyboard.last_apply_ms,sources=list(self.keyboard.sources),sim_dt_s=dt)
                    self.last_input_report=now
        except Exception as exc:self._fail(exc)
        finally:self.stats['max_step_ms']=max(self.stats['max_step_ms'],(time.monotonic()-started)*1000)
    def _read_state(self):
        snap=self.scene.motion.snapshot(self.scene.native_time());names={j['name'] for j in self.scene.motion.config['joints']}
        if not hasattr(self,'cached_mounts') or self.cached_mount_revision!=self.scene.poses.revision:
            self.cached_mounts=self.scene.poses.snapshot();self.cached_mount_revision=self.scene.poses.revision
        return {'schema_version':1,'snapshot_id':uuid.uuid4().hex,'session_id':self.session_id,'t_sim_s':self.time_s,
            'native_preview_time_s':self.scene.native_time(),'state_revision':self.revision,'mount_revision':self.scene.poses.revision,
            'position_world_m':list(snap['root_position']),'quaternion_xyzw':list(snap['root_xyzw']),
            'joints_deg':{n:math.degrees(v) for n,v in zip(snap['names'],snap['positions']) if n in names},
            'mounts':self.cached_mounts,'transition_kind':self.transition,'base_control':snap['base_control'],
            'horizontal':snap['horizontal'],'swing_zero_readback':snap['swing_zero_readback'],
            'native_step_index':self.clock.step_index,'native_epoch':self.clock.generation,'time_basis_version':2}
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
                'error':self.error,'playing':False,'keyboard_enabled':self.keyboard.enabled,'heartbeat_ns':time.monotonic_ns(),
                'recording_state':self.trajectory_phase,'trajectory_draining':bool(self.drains),
                'trajectory_path':self.last_trajectory,'trajectory_error':self.trajectory_error});return
        if not self.scene or not self.state:return
        pressed=self.keyboard.pressed()
        fast=self.job['interactive']['lightweight_publish']
        status={'phase':'interactive_ready','session_id':self.session_id,'heartbeat_ns':time.monotonic_ns(),
            'playing':self.playing,'keyboard_enabled':self.keyboard.enabled,'input_epoch':self.keyboard.input_epoch,
            'keyboard':self.keyboard.status(),'trajectory_draining':bool(self.drains),'state':self.state,'capture_snapshot':self.capture_state,
            'simulation_state':'initializing' if self.binding_pending and self.playing else self.timeline_state,
            'binding_ready':not self.binding_pending and self.timeline_state!='stopped',
            'recording_state':self.trajectory_phase,'trajectory_error':self.trajectory_error,
            'motion_state':self.lifecycle,'input_status':{'native_reason':self.native.reason if self.native else 'unavailable',
                'native_events':self.native.events if self.native else 0,'native_last_event':self.native.last_event if self.native else None,
                'focus':self.native.focus if self.native else {},'source':self.keyboard.active_source,
                'input_epoch':self.keyboard.input_epoch,'clear_reason':self.keyboard.reason,
                'error':self.last_input_error,'last_apply_ms':self.keyboard.last_apply_ms,'pressed':sorted(pressed),
                'log_dropped':self.log.dropped,'log_error':self.log.error},
            'metadata':self.metadata,'recording':self.recorder is not None,'trajectory_path':str(self.recorder.directory) if self.recorder else self.last_trajectory,
            'joint_controls':{k:asdict(v) for k,v in self.scene.motion.controller.states.items()},
            'tilt_controls':{k:asdict(v) for k,v in self.scene.motion.base_controller.tilt.states.items()},
            'statistics':{k:list(v) if isinstance(v,list) else v for k,v in self.stats.items()} if fast else self.stats,
            'socket':str(self.endpoint.path),'rate_factor':1.,'interaction_rate':self._rate_statistics()}
        # state/capture_state/metadata/mount generations are replaced, never edited after publication.
        if fast:self.endpoint.publish_owned(status)
        else:self.endpoint.publish(status)
    def command(self,m):
        if self.busy and m['action']!='close':raise ValueError('Controller lifecycle operation in progress')
        a=m['action'];p=m.get('payload',{});motion=self.scene.motion
        if a=='keys':
            self._require_binding()
            if not self.playing:raise ValueError('Motion paused; fresh key press required after Play')
            changed=self.keyboard.update(p.get('source','web'),p.get('keys',[]),p.get('input_epoch'),p.get('sequence'))
            if changed and p.get('keys'):self._hold_actual()
        elif a=='keyboard':return self.apply_keyboard(p)
        elif a=='play':self.scene.timeline.play();self.scene.timeline.commit();self._sync_timeline()
        elif a=='pause':self.scene.timeline.pause();self.scene.timeline.commit();self._sync_timeline()
        elif a=='motion':
            self.keyboard.clear('web_motion_command');self._hold_actual();self.scene.apply_commands(p);self._commit('direct')
        elif a=='hold':self.keyboard.clear('hold');self._hold_actual();self._commit()
        elif a=='mount':self._require_binding();self.scene.poses.apply(p['id'],p['position_m'],p['rotation_deg']);self._commit('direct')
        elif a=='save_mounts':return {'path':str(self.scene.poses.save())}
        elif a=='reset_mounts':self._require_binding();self.scene.poses.reset('web');self._commit('direct')
        elif a=='record_start':
            self._require_binding()
            if self.recorder or self.drains:raise ValueError('Trajectory is already recording or draining')
            directory=self.output/'trajectories'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
            metadata=dict(self.metadata,native_clock_origin_s=self.clock.origin,native_record_start_s=self.clock.last,
                native_epoch=self.clock.generation)
            self.recorder=TrajectoryRecorder(directory,metadata);self.trajectory_phase='recording';self.trajectory_error=None
            self._commit('direct');self.publish();return {'path':str(directory)}
        elif a=='record_stop':
            if not self.recorder:raise ValueError('No active trajectory')
            self.keyboard.clear('trajectory_end');self._hold_actual();self._commit()
            self.event('trajectory_end_requested');self._finish_recording('record_stop',message=m)
            return {'deferred':True}
        elif a in ('reset','stop'):
            self.scene.timeline.stop();self.scene.timeline.commit();self._sync_timeline()
            if a=='reset':self.scene.poses.reset('reset');self.cached_mount_revision=-1
        elif a=='exit':
            if self.recorder or self.drains:raise ValueError('End trajectory and wait for its applied receipt before exiting')
            self.busy=True;self.lifecycle='exiting';self.playing=False;self.keyboard.clear();self.native_keys.clear();self.publish()
            async def exit_session():
                try:
                    self._unsubscribe_simulation();self._unsubscribe_keyboard();await self.scene.close();self.lifecycle='exited'
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
        return {'state_revision':self.revision,'input_epoch':self.keyboard.input_epoch}
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
        started=time.monotonic();wall_dt=max(0,started-self.last_tick);self.last_tick=started
        if self.hot:self.hot.begin_frame()
        gap_ms=wall_dt*1000;self.stats['frame_gap_max_ms']=max(self.stats['frame_gap_max_ms'],gap_ms)
        self.stats['frame_gap_samples'].append(gap_ms)
        if len(self.stats['frame_gap_samples'])>256:del self.stats['frame_gap_samples'][0]
        if gap_ms>100 and started-self.last_gap_log>1:self.event('main_update_gap',wall_dt_ms=gap_ms,playing=self.playing);self.last_gap_log=started
        try:
            self.scene.check_stage()
            self._sync_timeline()
            if self.binding_pending and self.playing and time.monotonic()>self.binding_deadline:
                raise RuntimeError('Articulation binding did not become ready after Play')
            if not self.binding_pending and not self.scene.motion.ready:
                raise RuntimeError('Unexpected articulation handle loss outside native Stop')
            if self.native:self.native.poll_focus()
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
            if started-self.last_publish>.1:
                with self.span('status_publish'):self.publish()
                self.last_publish=started
        except Exception as exc:
            self._fail(exc)
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
        self.closed=True;self.playing=False;self._stop_rate_measurement();self.keyboard.clear();self.subscription=None
        self._unsubscribe_simulation()
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
