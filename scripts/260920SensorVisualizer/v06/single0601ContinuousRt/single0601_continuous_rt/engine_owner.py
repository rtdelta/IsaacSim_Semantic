"""Unique Kit/PhysX owner; prescribed motion pre-step, actual readback post-step."""
import asyncio
import json
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path
import numpy as np
from .common import ContractError, file_hash, save_json, source_ns, utc
from .geometry import rigid_pose
from .sensor_registry import build
from .sensor_backend import ContinuousBackend
from .state_ledger import StateLedger


class EngineOwner:
    def __init__(self, project, job, recording_id=None):
        import omni.kit.app
        import omni.usd
        import omni.timeline
        import carb.settings
        from isaacsim.core.simulation_manager import SimulationManager
        self.project, self.job = Path(project), job
        self.recording_id = recording_id or ('recording_' + uuid.uuid4().hex)
        self.epoch_id, self.scene_generation = 'epoch_' + uuid.uuid4().hex, 'scene_' + uuid.uuid4().hex
        self.capability_id = 'capability_' + uuid.uuid4().hex
        self.app, self.context = omni.kit.app.get_app(), omni.usd.get_context()
        self.timeline = omni.timeline.get_timeline_interface()
        self.manager, self.settings = SimulationManager, carb.settings.get_settings()
        self.ledger = StateLedger(job['capture']['state_history_max_records'])
        self.saved_settings, self.callback_ids = {}, []
        self.backend = self.motion = self.layer = None
        self.error = None
        self.on_receipt = lambda evidence, payload: None
        self.on_reject = lambda error: None
        self.on_state = lambda state: None
        self.moving = False
        self.state_revision = self.command_revision = 0
        self.last_step = None
        self.controller=self.native_keyboard=None
        self.on_control=lambda event:None
        self.pending_controls=[]
        self.closed=False
        self.pose_rig=None

    def setting(self, key, value):
        if key not in self.saved_settings:
            self.saved_settings[key] = self.settings.get(key)
        self.settings.set(key, value)

    async def initialize(self, open_scene=True):
        from pxr import Usd, Sdf, UsdGeom
        import omni.replicator.core as rep
        from isaacsim.core.rendering_manager import RenderingManager
        from isaacsim.core.simulation_manager import SimulationEvent
        from .robot.robot_discovery import discover_robots, bind_config
        from .robot.articulation_motion import ArticulationMotion
        from .robot.render_lease import RenderLease
        self.original_capture = self.settings.get('/omni/replicator/captureOnPlay')
        self.original_framerate = self.timeline.get_target_framerate()
        self.original_timeline_tcps=self.timeline.get_time_codes_per_second()
        runner=RenderingManager._loop_runner
        self.original_loop={'manual_mode':runner.get_manual_mode(),'manual_step_size':runner.get_manual_step_size()} if hasattr(runner,'get_manual_mode') else None
        # Fabric histories read these defaults at stage creation, not at later set_dt.
        for key in ('/app/runLoops/main/rateLimitEnabled','/app/runLoops/main/rateLimitFrequency',
                    '/app/settings/fabricDefaultSimPeriodNumerator','/app/settings/fabricDefaultSimPeriodDenominator'):
            self.saved_settings[key]=self.settings.get(key)
        self.setting('/app/settings/fabricDefaultSimPeriodNumerator',1)
        self.setting('/app/settings/fabricDefaultSimPeriodDenominator',self.job['clock']['physics_hz'])
        if open_scene:
            await self.context.open_stage_async(self.job['scene'])
        self.stage = self.context.get_stage()
        if not self.stage:
            raise ContractError('stage_missing', 'No loaded scene')
        until = time.monotonic() + 120
        while self.context.get_stage_loading_status()[2]:
            if time.monotonic() > until:
                raise ContractError('asset_loading', 'Stage loading timed out')
            await self.app.next_update_async()
        self.timeline.stop()
        await self.app.next_update_async()
        rep.orchestrator.set_capture_on_play(False)
        self.original_edit = self.stage.GetEditTarget()
        self.layer = Sdf.Layer.CreateAnonymous('Single0601ContinuousRt.usda')
        self.stage.GetSessionLayer().subLayerPaths.insert(0, self.layer.identifier)
        self.stage.SetEditTarget(self.layer)
        if float(UsdGeom.GetStageMetersPerUnit(self.stage)) != 1.0:
            raise ContractError('stage_units', 'Transplanted prescribed articulation currently requires metre stage')
        self.original_tcps = self.stage.GetTimeCodesPerSecond()
        cfg = json.loads((self.project/'config/robot_sensors.json').read_text())
        robots = [r for r in discover_robots(self.stage) if r['auto_eligible']]
        if len(robots) != 1:
            raise ContractError('robot_binding', 'Expected one supported prescribed excavator')
        self.robot_config = bind_config(cfg, robots[0])
        self.robot_config['robot_motion'].update(control_mode='scripted', reference_frame=cfg['root_frame'], horizontal_frame=cfg['horizontal_frame'])
        self.registry, self.sensor_overrides = build(self.stage, self.layer, cfg, self.job, self.recording_id)
        paths = [str(p.GetPath()) for p in self.stage.Traverse() if p.GetTypeName() in ('OmniLidar', 'Camera')]
        self.lease = RenderLease(self.stage, self.layer, paths)
        self.motion = ArticulationMotion(self.stage, self.layer, self.robot_config['robot_motion'], self._motion_error)
        before_attributes={str(a.GetPath()):a.Get() for p in self.stage.Traverse() for a in p.GetAttributes()
                           if a.GetName().startswith(('physics:','physxRigidBody:','drive:'))}
        self.motion.prepare()
        self.motion_overrides=[]
        for p in self.stage.Traverse():
            for a in p.GetAttributes():
                if a.GetName().startswith(('physics:','physxRigidBody:','drive:')):
                    before=before_attributes.get(str(a.GetPath()))
                    after=a.Get()
                    if isinstance(after,(bool,int,float,str)) and before!=after:
                        self.motion_overrides.append({'prim_path':str(p.GetPath()),'attribute':a.GetName(),'before':before,'after':after,
                            'usd_type':str(a.GetTypeName()),'unit':'boolean' if isinstance(after,bool) else 'native USD physics schema'})
        hz = self.job['clock']['physics_hz']
        self.manager.setup_simulation(dt=1.0/hz)
        RenderingManager.set_dt(1.0/hz)
        render = self.job['render']
        multitick=os.environ.get('S0601_FORCE_BARRIER')!='1' and self.job['capture']['backend']!='barrier'
        desired = {'/rtx/rendermode': render['mode'], '/rtx/post/dlss/execMode': render['dlss_mode'],
            '/rtx/post/aa/op': render['aa_mode'], '/rtx-transient/dlssg/enabled': False,
            '/rtx/post/motionblur/enabled': False, '/rtx/hydra/supportMultiTickRate': multitick,
            '/rtx/rendering/perSensorTickTlas': multitick, '/app/asyncRendering': False,
            '/renderer/raytracingMotion/enabled': multitick, '/rtx/scenedb/maxHistoryTransformCount': 64}
        for key, value in desired.items():
            self.setting(key, value)
        self.callback_ids.append(self.manager.register_callback(self._pre_physical_step, SimulationEvent.PHYSICS_PRE_STEP, order=-100))
        self.callback_ids.append(self.manager.register_callback(self._physical_step, SimulationEvent.PHYSICS_POST_STEP, order=100))
        self.timeline.play()
        self.timeline.commit()
        for _ in range(6):
            await self.app.next_update_async()
        if not self.motion.ready:
            raise ContractError('articulation_ready', 'Physical post-step did not initialize the articulation')
        self.timeline.pause()
        self.timeline.commit()
        if self.job['render'].get('sensor_pose_mode','mounted')=='usd_rig':
            from .render_pose_rig import RenderPoseRig
            self.pose_rig=RenderPoseRig(self.stage,self.layer,self.registry)
            initial=self.ledger.exact_time(self.epoch_id,source_ns(self.manager.get_simulation_time()))[1]
            self.pose_rig.update(initial['sensor_world_matrices_usd'])
        self.backend = ContinuousBackend(self.stage, self.layer, self.registry,
                                         lambda e, a: self.on_receipt(e, a), lambda e: self.on_reject(e), self.capability_id,
                                         native_trace=self.job.get('diagnostics',{}).get('native_trace',False))
        self.render_profile = {'schema_version': 1, 'recording_id': self.recording_id,
            'requested': render, 'effective': {key: self.settings.get(key) for key in desired},
            'settings': [{'path': key, 'requested': value, 'effective': self.settings.get(key), 'value_type': type(value).__name__} for key, value in desired.items()],
            'products': [{'sensor_id': w.entry['sensor_id'], 'render_product_path': p.path,
                          'resolution': [1920,1080] if w.kind == 'camera' else None} for w, p in zip(self.backend.writers, self.backend.products)],
            'original_products': self.lease.metadata()}
        self.render_profile['sensor_pose_mode']=self.job['render'].get('sensor_pose_mode','mounted')
        self.render_profile['render_pose_rig']=self.pose_rig.metadata if self.pose_rig else []
        rep.orchestrator.set_capture_on_play(True)

    def _motion_error(self, message):
        self.error = {'code': 'motion_failed', 'message': message}

    def _pre_physical_step(self, dt, context=None):
        try:
            if not self.motion.articulation.is_physics_tensor_entity_valid():
                return
            if self.motion.epoch is None:
                self.motion._capture_initial_state(self.manager.get_simulation_time())
            if self.controller is None:
                from .motion_controller import MotionController,NativeKeyboard
                self.controller=MotionController(self.motion,self.pending_controls.append)
                self.native_keyboard=NativeKeyboard(self.controller,lambda:self.timeline.is_playing())
            if self.moving and not getattr(self, '_moving_started', False):
                self.controller.enqueue('acceptance','base_velocity',{'speed_m_s':.3,'yaw_rate_deg_s':3.})
                self._moving_started = True
            applied=self.controller.step(float(dt),self.manager.get_num_physics_steps(),self.manager.get_simulation_time())
            if applied is not None:
                self.command_revision=applied
        except Exception as exc:
            self.error = {'code': getattr(exc, 'code', 'motion_pre_step'), 'message': str(exc)}

    def _physical_step(self, dt, context=None):
        from pxr import Usd, UsdGeom
        try:
            step = self.manager.get_num_physics_steps()
            native_time = self.manager.get_simulation_time()
            if self.last_step is not None and step != self.last_step + 1:
                raise ContractError('physics_discontinuity', 'Physical steps must be observed individually')
            self.last_step = step
            if not self.motion.ready:
                return
            actual = self.motion.snapshot(native_time)
            root = {'position_m': list(map(float, actual['root_position'])),
                    'orientation_xyzw': list(map(float, actual['root_xyzw']))}
            horizontal_matrix = UsdGeom.Xformable(self.stage.GetPrimAtPath(self.motion.horizontal_path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            hpos, hq = rigid_pose(np.array(horizontal_matrix))
            world_matrices = {entry['sensor_id']: np.array(UsdGeom.Xformable(self.stage.GetPrimAtPath(entry['prim_path'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).tolist()
                              for kind in ('cameras','lidars') for entry in self.registry[kind]}
            if self.pose_rig:
                self.pose_rig.update(world_matrices)
            self.state_revision += 1
            state = {'epoch_id': self.epoch_id, 'scene_generation': self.scene_generation, 'physical_step': step,
                'sim_time_ns': str(source_ns(native_time)), 'state_revision': self.state_revision, 'mount_revision': 0,
                'calibration_revision': 0, 'command_revision': self.command_revision,
                'snapshot_monotonic_ns': str(time.monotonic_ns()), 'root': root,
                'horizontal': {'position_m': hpos, 'orientation_xyzw': hq},
                'joints': {'names': actual['names'], 'types': ['revolute'] * len(actual['names']),
                           'position': actual['positions'], 'velocity': [], 'effort': [],
                           'velocity_source': 'unavailable', 'effort_source': 'unavailable'},
                'sensor_world_matrices_usd': world_matrices}
            self.ledger.publish(state)
            self.on_state(state)
            for event in self.pending_controls:
                self.on_control(dict(event,applied_physical_step=step,applied_simulation_time_ns=state['sim_time_ns'],
                                     applied_monotonic_ns=state['snapshot_monotonic_ns']))
            self.pending_controls.clear()
        except Exception as exc:
            self.error = {'code': getattr(exc, 'code', 'physical_step'), 'message': str(exc)}

    def environment(self):
        manager = self.app.get_extension_manager()
        def version(name):
            extension = manager.get_enabled_extension_id(name)
            return manager.get_extension_dict(extension).get('package', {}).get('version') if extension else None
        gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid,name,driver_version,memory.total', '--format=csv,noheader,nounits'], text=True).strip().split(', ')
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return {'schema_version': 1, 'recording_id': self.recording_id, 'host_id': platform.node(), 'created_utc': utc(),
            'os': {'name': platform.system(), 'version': platform.release(), 'architecture': platform.machine()},
            'versions': {'isaac_sim': Path('/root/isaacsim/VERSION').read_text().strip(), 'kit': self.app.get_build_version(),
                         'replicator': version('omni.replicator.core'), 'rtx_sensor': version('omni.sensors.nv.common'),
                         'ros_distro': 'jazzy', 'rosbag2': None, 'mcap_storage': None, 'python': platform.python_version()},
            'gpu': {'uuid': gpu[0], 'name': gpu[1], 'driver_version': gpu[2], 'total_memory_bytes': int(gpu[3])*1024*1024},
            'monotonic_clock': {'name': 'CLOCK_MONOTONIC', 'domain_id': boot, 'cross_process_verified': False}}

    def asset_manifest(self):
        from pxr import UsdUtils, Sdf, UsdGeom
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(self.job['scene']))
        dependencies = []
        for uri, kind in [(l.realPath or l.identifier, 'used_layer') for l in layers] + [(str(a), 'asset') for a in assets]:
            # USDZ members are hashed through the enclosing package, retaining the member URI.
            outer = uri.split('[',1)[0]
            p = Path(outer)
            local = p.is_file()
            dependencies.append({'uri': uri, 'kind': kind, 'resolved': local, 'sha256': file_hash(p) if local else None,
                                 'size_bytes': p.stat().st_size if local else None, 'reason': None if local else 'not a readable local file'})
        dependencies += [{'uri': str(uri), 'kind': 'unresolved', 'resolved': False, 'sha256': None, 'size_bytes': None, 'reason': 'USD resolver unresolved'} for uri in unresolved]
        return {'schema_version': 1, 'recording_id': self.recording_id, 'root_asset': self.job['scene'],
                'stage_meters_per_unit': float(UsdGeom.GetStageMetersPerUnit(self.stage)), 'stage_up_axis': str(UsdGeom.GetStageUpAxis(self.stage)),
                'dependencies': dependencies, 'session_overrides': self.sensor_overrides+self.motion_overrides,
                'prescribed_motion': {'gravity': 'disabled for robot', 'collision': 'disabled for robot', 'joint_drives': 'disabled for robot', 'contact_dynamics_validated': False}}

    async def close(self):
        if self.closed:
            return
        import omni.replicator.core as rep
        from isaacsim.core.rendering_manager import RenderingManager
        if self.backend:
            # Lifecycle drain only; never used to complete an individual formal group.
            self.backend.detach()
            rep.orchestrator.set_capture_on_play(False)
            await asyncio.wait_for(rep.orchestrator.stop_async(), timeout=15)
            self.backend.close()
        for callback in self.callback_ids:
            self.manager.deregister_callback(callback)
        self.callback_ids = []
        if self.native_keyboard:
            self.native_keyboard.close()
            self.native_keyboard=None
        if self.motion:
            self.motion.close()
        if self.pose_rig:
            self.pose_rig.close()
            self.pose_rig=None
        self.timeline.stop()
        self.timeline.commit()
        if self.layer:
            paths = self.stage.GetSessionLayer().subLayerPaths
            if self.layer.identifier in paths:
                paths.remove(self.layer.identifier)
            self.stage.SetEditTarget(self.original_edit)
        self.stage.SetTimeCodesPerSecond(self.original_tcps)
        self.timeline.set_time_codes_per_second(self.original_timeline_tcps)
        if self.original_loop:
            if self.original_loop['manual_step_size']>0:
                RenderingManager._loop_runner.set_manual_step_size(self.original_loop['manual_step_size'])
            RenderingManager._loop_runner.set_manual_mode(self.original_loop['manual_mode'])
        for key, value in self.saved_settings.items():
            if value is None:
                self.settings.destroy_item(key)
            else:
                self.settings.set(key, value)
        rep.orchestrator.set_capture_on_play(bool(self.original_capture))
        self.timeline.set_target_framerate(self.original_framerate)
        # Timeline setters queue state changes. Publish the restoration before
        # readback; no app update or physics/render step is needed at teardown.
        self.timeline.commit()
        restored={key:self.settings.get(key)==value for key,value in self.saved_settings.items()}
        timing={'stage_tcps':self.stage.GetTimeCodesPerSecond(),'timeline_tcps':self.timeline.get_time_codes_per_second(),
            'target_framerate':self.timeline.get_target_framerate()}
        loop_restored=not self.original_loop or (RenderingManager._loop_runner.get_manual_mode()==self.original_loop['manual_mode']
            and (self.original_loop['manual_step_size']<=0 or RenderingManager._loop_runner.get_manual_step_size()==self.original_loop['manual_step_size']))
        self.cleanup_report={'schema_version':1,'recording_id':self.recording_id,
            'owned_writer_count':len(self.backend.writers) if self.backend else 0,
            'owned_product_count':len(self.backend.products) if self.backend else 0,
            'physical_callback_count':len(self.callback_ids),'native_keyboard_closed':self.native_keyboard is None,
            'session_layer_removed':not self.layer or self.layer.identifier not in self.stage.GetSessionLayer().subLayerPaths,
            'settings_restored':restored,'timeline_stopped':not self.timeline.is_playing(),
            'timing_readback':timing,'timing_expected':{'stage_tcps':self.original_tcps,'timeline_tcps':self.original_timeline_tcps,'target_framerate':self.original_framerate},
            'target_framerate_restored':timing['target_framerate']==self.original_framerate,'loop_restored':loop_restored,
            'time_codes_restored':timing['stage_tcps']==self.original_tcps and timing['timeline_tcps']==self.original_timeline_tcps}
        self.cleanup_report['passed']=all(restored.values()) and self.cleanup_report['session_layer_removed'] and self.cleanup_report['time_codes_restored'] and self.cleanup_report['target_framerate_restored'] and loop_restored and self.cleanup_report['native_keyboard_closed'] and self.cleanup_report['timeline_stopped'] and not self.cleanup_report['owned_writer_count'] and not self.cleanup_report['owned_product_count'] and not self.cleanup_report['physical_callback_count']
        if not self.cleanup_report['passed']:
            raise ContractError('owner_cleanup','Actual owner cleanup or settings restoration failed')
        self.closed=True
        # Drop Python USD/articulation references before another case opens a stage.
        # The app context retains its own current stage; disk assets are never saved.
        self.on_receipt=lambda e,a:None
        self.on_reject=lambda e:None
        self.on_state=lambda s:None
        self.on_control=lambda e:None
        self.pending_controls.clear()
        self.motion=self.backend=self.layer=None
        self.stage=self.original_edit=self.lease=None
