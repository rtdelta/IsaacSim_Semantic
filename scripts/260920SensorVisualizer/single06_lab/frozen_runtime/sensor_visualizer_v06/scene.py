"""Native simulation-clock stepping and session-only scene ownership."""
from pathlib import Path
import hashlib
import json
import time
import uuid
import numpy as np
from .contracts import assert_frozen
from .diagnostics import NullDiagnostics
from .tickets import CaptureTicket, SampleError


class SceneStepper:
    def __init__(self, project, job, diagnostics=None):
        import omni.kit.app, omni.usd, omni.timeline
        from isaacsim.core.simulation_manager import SimulationManager
        self.diag=diagnostics or NullDiagnostics(); self.generation=uuid.uuid4().hex
        self.capture_id=None; self.on_phase=None; self.invalid=False; self.capture_failed=False; self.stage_subscription=None
        self.project, self.job = Path(project), job
        self.app = omni.kit.app.get_app(); self.context = omni.usd.get_context()
        self.timeline = omni.timeline.get_timeline_interface(); self.manager = SimulationManager
        self.layer = self.motion = self.drivers = self.poses = None
        self.saved_settings = {}; self.epoch_ns = None; self.closed = False

    def phase(self,name,**values):
        self.diag.context(phase=name,stage_generation=self.generation)
        self.diag.event('phase_changed',**values)
        if self.on_phase: self.on_phase(name,values)

    def check_stage(self):
        if self.invalid or self.context.get_stage()!=self.stage:
            self.invalid=True
            raise SampleError('resource_handle_invalid','Stage changed; close and reinitialize')

    def native_time(self): return self.manager.get_simulation_time()

    async def initialize(self, open_scene=True, sensor_products=True):
        self.phase("initializing")
        self.diag.set_manifest(job=self.job)
        import carb.settings
        import omni.replicator.core as rep
        from pxr import Usd, UsdGeom, UsdRender, Sdf
        from sensor_visualizer_v06.robot.robot_discovery import discover_robots, bind_config
        from sensor_visualizer_v06.robot.discovery import discover_sensors
        from sensor_visualizer_v06.robot.articulation_motion import ArticulationMotion
        from sensor_visualizer_v06.robot.render_lease import RenderLease
        from sensor_visualizer_v06.robot.sensor_pose import SensorPoses
        from .sensors import SensorDrivers
        settings = carb.settings.get_settings()
        self.original_capture_on_play = settings.get('/omni/replicator/captureOnPlay')
        self.original_target_framerate = self.timeline.get_target_framerate()
        rep.orchestrator.set_capture_on_play(False)
        if open_scene:
            with self.diag.span('scene_open'):
                await self.context.open_stage_async(self.job['scene'])
        self.stage = self.context.get_stage()
        if not self.stage: raise RuntimeError('Open a combine stage first')
        def stage_guard(_):
            if not self.closed and not self.invalid and self.context.get_stage()!=self.stage:
                self.invalid=True
                self.diag.warning('resource_handle_invalid','Stage replaced; reinitialize required')
                self.phase('stage_invalid')
        self.stage_subscription=self.app.get_update_event_stream().create_subscription_to_pop(stage_guard,name='SV06 stage ownership')
        deadline = time.monotonic()+120
        while self.context.get_stage_loading_status()[2]:
            if time.monotonic()>deadline: raise TimeoutError('Assets did not finish USD loading')
            await self.app.next_update_async()
        self.timeline.stop()
        await self.app.next_update_async()
        # Opening a new USD stage resets Replicator's capture-on-play setting.
        # Apply after stage-load/STOP callbacks, before creating tensor views;
        # otherwise stop/drain also stops Timeline and invalidates Articulation.
        rep.orchestrator.set_capture_on_play(False)
        self.diag.event('capture_on_play_disabled',after_stage_load=True,
                        actual=settings.get('/omni/replicator/captureOnPlay'))
        if abs(UsdGeom.GetStageMetersPerUnit(self.stage)-1) > 1e-9: raise ValueError('Expected metre stage')
        self.original_edit_target = self.stage.GetEditTarget()
        self.layer = Sdf.Layer.CreateAnonymous('SensorVisualizerV06.usda')
        self.stage.GetSessionLayer().subLayerPaths.insert(0,self.layer.identifier)
        self.stage.SetEditTarget(self.layer)
        from .lighting import select_dome
        self.lighting=select_dome(self.stage,self.layer,self.job['render']['background_dome'],
                                  self.job['capture']['backend'],self.diag)
        cfg = json.loads((self.project/'config/robot_sensors.json').read_text())
        robots = [r for r in discover_robots(self.stage) if r['auto_eligible']]
        if len(robots)!=1: raise RuntimeError('Expected one supported excavator')
        self.config = cfg = bind_config(cfg,robots[0])
        cfg['robot_motion'].update(control_mode='scripted', reference_frame=cfg['root_frame'], horizontal_frame=cfg['horizontal_frame'])
        all_lidars = discover_sensors(self.stage, robot_path=cfg['robot_motion']['robot_prim'])
        chosen = self.job['sensors']['lidar_ids']
        lidars = all_lidars if chosen is None else [s for s in all_lidars if s['id'] in chosen]
        if chosen is not None and set(chosen)!=set(s['id'] for s in lidars): raise ValueError('Unknown LiDAR ID')
        for lidar in lidars:
            prim = self.stage.GetPrimAtPath(lidar['prim_path'])
            if not prim.GetAttribute('omni:sensor:Core:instantLidar').Get(): raise ValueError('Only Instant LiDAR supported: '+lidar['id'])
            lidar['parameters'] = {a.GetName():str(a.Get()) for a in prim.GetAttributes() if any(k in a.GetName() for k in ('instantLidar','scanType','scanRateBaseHz','tickRate','nearRange','farRange'))}
        cameras = []
        chosen_cameras = self.job['sensors']['camera_ids']
        all_cameras = []
        for item in cfg['cameras']:
            path = item['prim_path']
            if item['id']=='back' and not self.stage.GetPrimAtPath(path): path = path.replace('FisheyeBack','FisheyeRear')
            prim = self.stage.GetPrimAtPath(path)
            if not prim or not prim.IsA(UsdGeom.Camera): raise ValueError('Missing camera '+path)
            all_cameras.append(path)
            if chosen_cameras is not None and item['id'] not in chosen_cameras: continue
            if prim.GetAttribute('omni:lensdistortion:model').Get()!='opencvFisheye': raise ValueError('Expected calibrated fisheye')
            width,height = map(int,prim.GetAttribute('omni:lensdistortion:opencvFisheye:imageSize').Get())
            intrinsics = {n:float(prim.GetAttribute('omni:lensdistortion:opencvFisheye:'+n).Get()) for n in ('fx','fy','cx','cy','k1','k2','k3','k4')}
            cameras.append({'id':item['id'],'prim_path':path,'calibration':{'model':'opencv_fisheye','width':width,'height':height,
                'intrinsics':intrinsics,'exposure':{a.GetName():a.Get() for a in prim.GetAttributes() if a.GetName().startswith('exposure:')},
                'camera_usd_axes':'X right, Y up, -Z forward','camera_optical_axes':'X right, Y down, Z forward'}})
        if chosen_cameras is not None and set(chosen_cameras)!=set(c['id'] for c in cameras): raise ValueError('Unknown camera ID')
        if not cameras or not lidars: raise ValueError('Select at least one camera and one Instant LiDAR')
        self.registry = {'schema_version':2,'lidars':lidars,'cameras':cameras,
                         'world_frame':'world','root_frame':'swing_coordinate','horizontal_frame':'swing_horizontal_coordinate'}
        self.lease = RenderLease(self.stage,self.layer,[s['prim_path'] for s in all_lidars]+all_cameras)
        self.motion = ArticulationMotion(self.stage,self.layer,cfg['robot_motion'],lambda message: print('[SV06 motion] '+message,flush=True))
        self.motion.performance=self.diag
        self.motion.cache_enabled=bool(not sensor_products and self.job['interactive']['motion_cache'])
        self.motion.prepare()
        self.timeline.set_target_framerate(self.job['physics_hz'])
        self.timeline.play(); self.timeline.commit()
        for _ in range(6): await self.app.next_update_async()
        self.timeline.pause(); self.timeline.commit()
        self.motion.tick(self.native_time())
        if not self.motion.ready: raise RuntimeError('Articulation did not initialize')
        mounts=lidars+[dict(c,id='camera_'+c['id']) for c in cameras]
        self.poses = SensorPoses(self.stage,mounts,self.job['output_directory'],self.native_time)
        for sid,row in self.job['mount_poses'].items(): self.poses.apply(sid,row['position_m'],row['rotation_deg'])
        self.apply_commands(self.job['motion'])
        if not sensor_products:
            # Interactive context has articulation + viewport, no formal products.
            profile=self.job['render']
            desired={'/rtx/rendermode':profile['mode'],'/rtx/post/dlss/execMode':profile['dlss_mode'],
                     '/rtx/post/aa/op':profile['aa_mode'],'/rtx-transient/dlssg/enabled':False,
                     '/app/runLoops/main/rateLimitEnabled':True,'/app/runLoops/main/rateLimitFrequency':60}
            for name,value in desired.items():
                self.saved_settings[name]=settings.get(name); settings.set(name,value)
            self.epoch_ns=round(self.native_time()*1e9)
            self.render_actual={'requested':profile,'sensor_products_created':False,'render_lease':self.lease.metadata(),
                                'lighting':self.lighting,'native_epoch_ns':self.epoch_ns}
            source=Path(self.stage.GetRootLayer().realPath)
            self.asset_manifest={'root_layer':str(source),'root_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            self.phase('interactive_ready')
            return
        with self.diag.span('sensor_initialize'):
            self.drivers = await SensorDrivers.create(self.stage,self.layer,self.registry,self.diag,self.generation,
                                                     self.app,self.check_stage,backend=self.job['capture']['backend'])
        self.drivers.progress=lambda pending:self.phase('waiting_data',pending=pending)
        profile = self.job['render']
        desired = {'/rtx/rendermode':profile['mode'], '/rtx/post/dlss/execMode':profile['dlss_mode'],
                   '/rtx/post/aa/op':profile['aa_mode'], '/rtx-transient/dlssg/enabled':False,
                   '/app/runLoops/main/rateLimitEnabled':False, '/app/asyncRendering':False}
        for name,value in desired.items():
            self.saved_settings[name] = settings.get(name); settings.set(name,value)
        for prim in self.stage.Traverse():
            if prim.IsA(UsdRender.Settings):
                for name,value in {'omni:rtx:rendermode':profile['mode'], 'omni:rtx:post:dlss:execMode':('performance','balanced','quality','auto')[profile['dlss_mode']]}.items():
                    attr = prim.GetAttribute(name)
                    if attr: attr.Set(value)
        await self.drivers.render(profile['warmup_subframes'])
        # Replicator initializes the native clock before the recording epoch.
        self.motion._apply_controlled_base(self.motion._command_angles())
        await self.drivers.render(profile['warmup_subframes'])
        self.epoch_ns = round(self.native_time()*1e9)
        self.timeline_epoch = self.timeline.get_current_time()
        self.render_actual = {'requested':profile,'settings':{name:settings.get(name) for name in desired},
                              'native_epoch_ns':self.epoch_ns,'timeline_epoch_s':self.timeline_epoch,
                              'initialization_capture_excluded':True,'render_lease':self.lease.metadata(),
                              'lighting':self.lighting}
        source=Path(self.stage.GetRootLayer().realPath)
        self.asset_manifest={'root_layer':str(source),'root_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'stage_pending_at_ready':list(self.context.get_stage_loading_status()),
            'used_layers':[{'identifier':l.identifier,'bytes':Path(l.realPath).stat().st_size} for l in self.stage.GetUsedLayers()
                           if l.realPath and Path(l.realPath).is_file()],
            'note':'USD loaded plus frozen render warmup; USD loading status alone does not prove GPU texture residency.'}
        self.drivers.suspend_all('idle')
        self.rendered_pose_revision=self.poses.revision
        self.diag.set_manifest(asset_manifest=self.asset_manifest,render_actual=self.render_actual)
        self.phase('idle')

    def apply_commands(self, commands):
        with self.motion.batch_updates():self._apply_commands(commands)

    def _apply_commands(self, commands):
        self.check_stage()
        self.diag.event('motion_command_applied',command=commands)
        motion = self.motion
        initial=commands.get('_initial',{})
        if initial.get('joints'): motion.command('execute',commands={n:{'mode':'direct','target':v} for n,v in initial['joints'].items()})
        if initial.get('tilt'): motion.command_tilt('execute',commands={n:{'mode':'direct','target':v} for n,v in initial['tilt'].items()})
        if commands.get('joints'):
            mapped = {}
            roles = {j['role']:j['name'] for j in motion.config['joints']}
            for role,command in commands['joints'].items(): mapped[roles.get(role,role)] = command
            motion.command('execute',commands=mapped)
        if commands.get('tilt'): motion.command_tilt('execute',commands=commands['tilt'])
        for kind,controller in (('joints',motion.controller),('tilt',motion.base_controller.tilt)):
            for name,direction in initial.get(kind+'_directions',{}).items():
                if direction not in (-1,1): raise ValueError('Periodic direction must be +/-1')
                controller.states[name].direction=direction
        base = commands.get('base',{})
        if base:
            c = motion.base_controller
            if any(k in base for k in ('x','y','yaw_deg')):
                motion.command_base('direct',x=base.get('x',c.x),y=base.get('y',c.y),yaw_deg=base.get('yaw_deg',np.rad2deg(c.heading)))
            if 'z' in base: motion.command_base('height',z=base['z'])
            if 'speed_m_s' in base or 'yaw_rate_deg_s' in base:
                motion.command_base('velocity',speed=base.get('speed_m_s',0),yaw_rate_deg=base.get('yaw_rate_deg_s',0))

    async def advance(self, group):
        self.check_stage(); self.phase('advancing')
        self.drivers.suspend_all('advance')
        if group == 0: return
        self.drivers.suspend_all('idle')
        dt = 1/self.job['physics_hz']
        # Kit updates also synchronize the RTX graph clock. Direct native stepping
        # is faster but failed the source-clock contract on Isaac 6.0.1-rc.7.
        self.timeline.set_auto_update(True)
        self.timeline.play(); self.timeline.commit()
        try:
            for _ in range(round(self.job['physics_hz']/self.job['sample_hz'])):
                with self.diag.span('motion_compute',group_id=group):
                    self.motion.controller.step(dt); self.motion.base_controller.step(dt)
                with self.diag.span('pose_apply',group_id=group):
                    self.motion._apply_controlled_base(self.motion._command_angles())
                with self.diag.span('kit_motion_update',group_id=group):
                    await self.app.next_update_async()
                self.check_stage()
                self.diag.event('native_clock_step',simulation_time_ns=round(self.native_time()*1e9),detail=True)
        finally:
            self.timeline.pause(); self.timeline.commit()
        self.motion._apply_controlled_base(self.motion._command_angles())

    async def capture(self, group, stamp_ns):
        self.diag.context(group_id=group,simulation_time_ns=stamp_ns)
        self.check_stage(); self.phase('freeze')
        before=self.native_time(); timeline_before=self.timeline.get_current_time()
        pose_before=self._pose_matrices(); revision=self.poses.revision
        if abs(round(before*1e9)-stamp_ns)>2:
            raise SampleError('source_time_mismatch',f'Native clock grid mismatch {before} vs {stamp_ns}')
        def frozen():
            self.check_stage()
            try:
                assert_frozen(before,self.native_time()); assert_frozen(timeline_before,self.timeline.get_current_time())
            except RuntimeError as exc: raise SampleError('scene_changed_while_frozen',str(exc)) from exc
            if self.poses.revision!=revision: raise SampleError('scene_changed_while_frozen','Mount revision changed')
            current=self._pose_matrices()
            if current.keys()!=pose_before.keys(): raise SampleError('scene_changed_while_frozen','Scene topology changed')
            for path,matrix in current.items():
                if not np.allclose(matrix,pose_before[path],rtol=0,atol=2e-6):
                    raise SampleError('scene_changed_while_frozen','Pose changed: '+path)
        start=time.perf_counter(); warm_start=start
        expected=frozenset(kind+'/'+e['id'] for kind in ('cameras','lidars') for e in self.registry[kind])
        try:
            self.phase('warmup')
            if revision!=self.rendered_pose_revision:
                with self.diag.span('mount_notice_update'): await self.app.next_update_async()
                await self.drivers.render(self.job['render']['warmup_subframes']); frozen()
            if self.job['render']['camera_subframes']>1:
                await self.drivers.warm_cameras(self.job['render']['camera_subframes']); frozen()
            warm_s=time.perf_counter()-warm_start; retry_s=0
            for attempt in range(self.job['capture']['max_retries']+1):
                self.phase('capture',attempt_id=attempt)
                ticket=CaptureTicket(self.diag.run_id,self.capture_id,group,self.generation,stamp_ns,revision,
                                     expected,self.job['capture']['ready_timeout_s'],attempt_id=attempt)
                retry_start=time.perf_counter()
                try:
                    arrays,cameras,lidars=await self.drivers.acquire(ticket,self.job['render']['capture_subframes'],
                        self.app,frozen,self.job['capture']['max_progress_updates'])
                    break
                except SampleError as exc:
                    # Retry only completed, delivered requests. Missing callbacks
                    # retain their old bindings and cannot be assigned to a new group.
                    if exc.reason not in ('source_time_mismatch','render_pose_mismatch','source_frame_stale') or attempt>=self.job['capture']['max_retries']:
                        raise
                    self.diag.event('capture_retry',critical=True,reason=exc.reason,
                                    scope='whole_group',sensor_id=exc.sensor_id,**ticket.identity())
                    frozen()
                finally:
                    if attempt: retry_s+=time.perf_counter()-retry_start
            frozen(); self.rendered_pose_revision=revision
            self.last_capture_timings={'render_and_readback_total':time.perf_counter()-start,
                                      'camera_and_mount_warmup':warm_s,'freshness_retry':retry_s}
            snapshot=self.motion.snapshot(before)
            return arrays, {**ticket.identity(),'simulation_time_ns':stamp_ns,
                'elapsed_simulation_ns':stamp_ns-self.epoch_ns,'source_clock_before_s':before,
                'source_clock_after_s':self.native_time(),'timeline_time_s':timeline_before,
                'pose_revision':revision,'frozen_render_retries':attempt,
                'robot':snapshot,'cameras':cameras,'lidars':lidars}
        finally:
            self.drivers.suspend_all('capture_boundary')

    def _pose_matrices(self):
        from pxr import UsdGeom, Usd
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        paths = [s['prim_path'] for kind in ('lidars','cameras') for s in self.registry[kind]]
        paths += [self.config['robot_motion']['robot_prim']]
        paths += [str(path) for path,_ in self.motion.saved_xforms]
        return {p:np.asarray(cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(p))) for p in paths}

    def apply_snapshot(self,state):
        """Apply the complete reference pose, without Euler reconstruction."""
        from .trajectory import validate_state
        validate_state(state); self.check_stage()
        motion=self.motion; names={j['name'] for j in motion.config['joints']}
        if set(state['joints_deg'])!=names: raise ValueError('Snapshot joint mapping differs from asset')
        for name,angle in state['joints_deg'].items():
            s=motion.controller.states[name]
            if not s.minimum-1e-4<=angle<=s.maximum+1e-4:raise ValueError('Snapshot exceeds joint limit: '+name)
        # Validate mappings before authoring the captured state.
        if {r['id'] for r in state['mounts']}!=set(self.poses.entries):raise ValueError('Snapshot sensor mapping differs')
        for row in state['mounts']:
            current=self.poses.read(row['id'])
            if any(abs(a-b)>1e-7 for a,b in zip(current['position_m']+current['rotation_deg'],row['position_m']+row['rotation_deg'])):
                self.poses.apply(row['id'],row['position_m'],row['rotation_deg'])
        for name,angle in state['joints_deg'].items():
            s=motion.controller.states[name];s.angle=s.target=angle;s.running=False
        q=state['quaternion_xyzw']; reference=motion._root_matrix(state['position_world_m'],[q[3],*q[:3]])
        root=motion.reference_in_root.GetInverse()*reference; rq=root.ExtractRotationQuat().GetNormalized()
        motion._apply(root.ExtractTranslation(),motion._command_angles(),[rq.GetReal(),*rq.GetImaginary()])
        import math
        x,y,z,w=q;c=motion.base_controller;c.x,c.y,c.z=state['position_world_m']
        c.heading=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z));c.speed=c.yaw_rate=0
        c.tilt.states['pitch'].angle=math.degrees(math.asin(max(-1,min(1,2*(w*y-z*x))))-c.initial_pitch)
        c.tilt.states['roll'].angle=math.degrees(math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))-c.initial_roll)
        for value in c.tilt.states.values():value.running=False

    async def advance_clock(self,elapsed_s):
        """Advance native source clock on physics grid, never fake message headers."""
        target_steps=round(float(elapsed_s)*self.job['physics_hz'])
        current_steps=round((round(self.native_time()*1e9)-self.epoch_ns)/1e9*self.job['physics_hz'])
        if target_steps<current_steps:raise ValueError('Capture clock cannot move backwards')
        self.drivers.suspend_all('advance')
        self.timeline.set_auto_update(True);self.timeline.play();self.timeline.commit()
        try:
            for _ in range(target_steps-current_steps):
                await self.app.next_update_async();self.check_stage()
        finally:
            self.timeline.pause();self.timeline.commit()
        actual_steps=round((round(self.native_time()*1e9)-self.epoch_ns)/1e9*self.job['physics_hz'])
        if actual_steps!=target_steps:raise SampleError('source_time_mismatch',f'Native steps {actual_steps} != trajectory steps {target_steps}')

    async def close(self):
        if self.closed:return
        self.phase('closing')
        import carb.settings
        same_stage=hasattr(self,'stage') and self.context.get_stage()==self.stage
        errors=[]
        def attempt(name,fn):
            try: fn()
            except Exception as exc:
                errors.append(name+': '+str(exc));self.diag.warning('cleanup_failed',str(exc),operation=name)
        if same_stage:
            self.timeline.pause();self.timeline.commit()
        if self.drivers:
            if self.drivers.inflight is not None:
                # The capture owner normally completes this before close.
                import asyncio
                await asyncio.shield(self.drivers.inflight)
            if getattr(self.drivers,'generation_open',False):
                await self.drivers._drain_generation()
            attempt('suspend_products',lambda:self.drivers.suspend_all('close'))
            attempt('detach',self.drivers.detach)
            await self.app.next_update_async()
            attempt('destroy_products',self.drivers.destroy)
            await self.app.next_update_async()
        if same_stage:
            # Finish PhysX while the runtime authoring target still exists;
            # removing that layer while paused leaves tensor views live.
            self.timeline.stop();self.timeline.commit()
            await self.app.next_update_async()
        if self.motion:attempt('motion_restore',lambda:self.motion.close(restore=same_stage))
        if self.poses:attempt('mount_restore',self.poses.close)
        if self.layer:
            def remove_layer():
                self.stage.SetEditTarget(self.original_edit_target)
                session=self.stage.GetSessionLayer()
                if self.layer.identifier in session.subLayerPaths:session.subLayerPaths.remove(self.layer.identifier)
            attempt('session_layer_remove',remove_layer)
        settings=carb.settings.get_settings()
        if hasattr(self,'original_target_framerate'):
            attempt('restore_framerate',lambda:self.timeline.set_target_framerate(self.original_target_framerate))
        if hasattr(self,'original_capture_on_play'):
            self.saved_settings['/omni/replicator/captureOnPlay']=self.original_capture_on_play
        for name,value in self.saved_settings.items():
            attempt('restore_setting '+name,lambda n=name,v=value:settings.destroy_item(n) if v is None else settings.set(n,v))
        self.stage_subscription=None;self.closed=True
        self.diag.event('scene_closed',critical=True,cleanup_errors=errors)
        if errors:raise RuntimeError('Scene cleanup incomplete: '+'; '.join(errors))
