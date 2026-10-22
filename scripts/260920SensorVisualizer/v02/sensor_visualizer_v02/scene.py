"""Native simulation-clock stepping and session-only scene ownership."""
from pathlib import Path
import hashlib
import json
import time
import numpy as np
from .contracts import assert_frozen


class SceneStepper:
    def __init__(self, project, job):
        import omni.kit.app, omni.usd, omni.timeline
        from isaacsim.core.simulation_manager import SimulationManager
        self.project, self.job = Path(project), job
        self.app = omni.kit.app.get_app(); self.context = omni.usd.get_context()
        self.timeline = omni.timeline.get_timeline_interface(); self.manager = SimulationManager
        self.layer = self.motion = self.drivers = self.poses = None
        self.saved_settings = {}; self.epoch_ns = None; self.closed = False

    def native_time(self): return self.manager.get_simulation_time()

    async def initialize(self, open_scene=True):
        import carb.settings
        import omni.replicator.core as rep
        from pxr import Usd, UsdGeom, UsdRender, Sdf
        from sv02_legacy.robot_discovery import discover_robots, bind_config
        from sv02_legacy.discovery import discover_sensors
        from sv02_legacy.articulation_motion import ArticulationMotion
        from sv02_legacy.render_lease import RenderLease
        from sv02_legacy.sensor_pose import SensorPoses
        from .sensors import SensorDrivers
        settings = carb.settings.get_settings()
        self.original_capture_on_play = settings.get('/omni/replicator/captureOnPlay')
        self.original_target_framerate = self.timeline.get_target_framerate()
        rep.orchestrator.set_capture_on_play(False)
        if open_scene:
            await self.context.open_stage_async(self.job['scene'])
        self.stage = self.context.get_stage()
        if not self.stage: raise RuntimeError('Open a combine stage first')
        deadline = time.monotonic()+120
        while self.context.get_stage_loading_status()[2]:
            if time.monotonic()>deadline: raise TimeoutError('Assets did not finish USD loading')
            await self.app.next_update_async()
        self.timeline.stop()
        await self.app.next_update_async()
        if abs(UsdGeom.GetStageMetersPerUnit(self.stage)-1) > 1e-9: raise ValueError('Expected metre stage')
        self.original_edit_target = self.stage.GetEditTarget()
        self.layer = Sdf.Layer.CreateAnonymous('SensorVisualizerV02.usda')
        self.stage.GetSessionLayer().subLayerPaths.insert(0,self.layer.identifier)
        self.stage.SetEditTarget(self.layer)
        cfg = json.loads((self.project/'config/legacy_sensors.json').read_text())
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
        self.motion = ArticulationMotion(self.stage,self.layer,cfg['robot_motion'],lambda message: print('[SV02 motion] '+message,flush=True))
        self.motion.prepare()
        self.timeline.set_target_framerate(self.job['physics_hz'])
        self.timeline.play(); self.timeline.commit()
        for _ in range(6): await self.app.next_update_async()
        self.timeline.pause(); self.timeline.commit()
        self.motion.tick(self.native_time())
        if not self.motion.ready: raise RuntimeError('Articulation did not initialize')
        self.poses = SensorPoses(self.stage,lidars,self.job['output_directory'],self.native_time)
        for sid,row in self.job['mount_poses'].items(): self.poses.apply(sid,row['position_m'],row['rotation_deg'])
        self.apply_commands(self.job['motion'])
        self.drivers = SensorDrivers(self.stage,self.layer,self.registry)
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
                              'initialization_capture_excluded':True,'render_lease':self.lease.metadata()}
        source=Path(self.stage.GetRootLayer().realPath)
        self.asset_manifest={'root_layer':str(source),'root_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'stage_pending_at_ready':list(self.context.get_stage_loading_status()),
            'used_layers':[{'identifier':l.identifier,'bytes':Path(l.realPath).stat().st_size} for l in self.stage.GetUsedLayers()
                           if l.realPath and Path(l.realPath).is_file()],
            'note':'USD loaded plus frozen render warmup; USD loading status alone does not prove GPU texture residency.'}
        self.drivers.enabled(False)
        self.rendered_pose_revision=self.poses.revision

    def apply_commands(self, commands):
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
        if group == 0: return
        self.drivers.enabled(False)
        dt = 1/self.job['physics_hz']
        # Kit updates also synchronize the RTX graph clock. Direct native stepping
        # is faster but failed the source-clock contract on Isaac 6.0.1-rc.7.
        self.timeline.play(); self.timeline.commit()
        try:
            for _ in range(round(self.job['physics_hz']/self.job['sample_hz'])):
                self.motion.controller.step(dt); self.motion.base_controller.step(dt)
                self.motion._apply_controlled_base(self.motion._command_angles())
                await self.app.next_update_async()
        finally:
            self.timeline.pause(); self.timeline.commit()
        self.motion._apply_controlled_base(self.motion._command_angles())

    async def capture(self, group, stamp_ns):
        from .sensors import StaleSample
        before = self.native_time(); timeline_before = self.timeline.get_current_time()
        pose_before = self._pose_matrices()
        if abs(round(before*1e9)-stamp_ns)>2: raise RuntimeError(f'Native clock grid mismatch {before} vs {stamp_ns}')
        t=time.perf_counter()
        if self.poses.revision!=self.rendered_pose_revision:
            # Mount edits change a USD transform outside the articulation tensor.
            # Flush its notice and settle RTX at the same paused time before use.
            await self.app.next_update_async()
            await self.drivers.render(self.job['render']['warmup_subframes'])
        warm_start=time.perf_counter()
        if self.job['render']['camera_subframes']>1:
            await self.drivers.warm_cameras(self.job['render']['camera_subframes'])
        camera_warm_s=time.perf_counter()-warm_start
        await self.drivers.render(self.job['render']['capture_subframes'])
        render_s=time.perf_counter()-t
        assert_frozen(before,self.native_time()); assert_frozen(timeline_before,self.timeline.get_current_time())
        for path, matrix in self._pose_matrices().items():
            if not np.allclose(matrix, pose_before[path], rtol=0, atol=2e-6):
                raise RuntimeError('Scene pose changed during capture: '+path)
        retries=0; read_s=0.; retry_s=0.
        while True:
            read_start=time.perf_counter()
            try:
                arrays,cameras,lidars = self.drivers.read(stamp_ns)
                read_s+=time.perf_counter()-read_start
                break
            except StaleSample:
                read_s+=time.perf_counter()-read_start
                if retries>=3: raise
                retries+=1
                # RTX/OmniGraph can deliver a prior product after a pause or edit.
                # Retry at the same scene and time; never relabel the old result.
                retry_start=time.perf_counter()
                await self.drivers.render(self.job['render']['capture_subframes'])
                retry_s+=time.perf_counter()-retry_start
                assert_frozen(before,self.native_time()); assert_frozen(timeline_before,self.timeline.get_current_time())
                for path,matrix in self._pose_matrices().items():
                    if not np.allclose(matrix,pose_before[path],rtol=0,atol=2e-6):
                        raise RuntimeError('Scene changed during frozen retry: '+path)
        self.last_capture_timings={'render':render_s+retry_s,'camera_warmup':camera_warm_s,
                                   'freshness_retry_render':retry_s,'readback_validation':read_s}
        self.rendered_pose_revision=self.poses.revision
        snapshot = self.motion.snapshot(before)
        self.drivers.enabled(False)
        return arrays, {'group_id':group,'simulation_time_ns':stamp_ns,'elapsed_simulation_ns':stamp_ns-self.epoch_ns,
                        'source_clock_before_s':before,'source_clock_after_s':self.native_time(),
                        'timeline_time_s':timeline_before,'pose_revision':self.poses.revision,'frozen_render_retries':retries,
                        'robot':snapshot,'cameras':cameras,'lidars':lidars}

    def _pose_matrices(self):
        from pxr import UsdGeom, Usd
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        paths = [s['prim_path'] for kind in ('lidars','cameras') for s in self.registry[kind]]
        paths += [self.config['robot_motion']['robot_prim']]
        paths += [str(path) for path,_ in self.motion.saved_xforms]
        return {p:np.asarray(cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(p))) for p in paths}

    async def close(self):
        if self.closed: return
        self.closed=True
        import carb.settings
        self.timeline.pause(); self.timeline.commit()
        if self.drivers:
            self.drivers.enabled(False); self.drivers.detach()
            await self.app.next_update_async()
            self.drivers.destroy()
            await self.app.next_update_async()
        if self.motion: self.motion.close()
        if self.poses: self.poses.close()
        if self.layer:
            self.stage.SetEditTarget(self.original_edit_target)
            session = self.stage.GetSessionLayer()
            if self.layer.identifier in session.subLayerPaths: session.subLayerPaths.remove(self.layer.identifier)
        settings=carb.settings.get_settings()
        if hasattr(self,'original_target_framerate'): self.timeline.set_target_framerate(self.original_target_framerate)
        if hasattr(self,'original_capture_on_play'):
            if self.original_capture_on_play is None: settings.destroy_item('/omni/replicator/captureOnPlay')
            else: settings.set('/omni/replicator/captureOnPlay',self.original_capture_on_play)
        for name,value in self.saved_settings.items():
            if value is None: settings.destroy_item(name)
            else: settings.set(name,value)
