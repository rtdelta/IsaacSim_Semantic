"""Minimal native USD sensor + asymmetric room, driven by real physics clock."""
import math
import time
import numpy as np
from .engine_owner import EngineOwner
from .sensor_backend import ContinuousBackend
from .sensor_registry import attributes
from .geometry import matrix_from_pose,rigid_pose
from .common import ContractError,source_ns


class NativeProbeOwner(EngineOwner):
    """Diagnostic scene only: no robot or formal contact-dynamics claim."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.profile={'speed_m_s':0.,'yaw_rate_deg_s':0.}
        self.position=np.zeros(3);self.heading=0.
        self.room_geometry=[]
    def set_profile(self,profile):self.profile=dict(profile)
    async def initialize(self,open_scene=True,sensor_products=True):
        from pxr import Usd,UsdGeom,Sdf,Gf
        import omni.replicator.core as rep
        from isaacsim.core.rendering_manager import RenderingManager
        from isaacsim.core.simulation_manager import SimulationEvent
        self.original_capture=self.settings.get('/omni/replicator/captureOnPlay')
        self.original_framerate=self.timeline.get_target_framerate()
        self.original_timeline_tcps=self.timeline.get_time_codes_per_second()
        runner=RenderingManager._loop_runner
        self.original_loop={'manual_mode':runner.get_manual_mode(),'manual_step_size':runner.get_manual_step_size()}
        self.setting('/app/settings/fabricDefaultSimPeriodNumerator',1)
        hz=self.job['clock']['physics_hz']
        self.setting('/app/settings/fabricDefaultSimPeriodDenominator',hz)
        await self.context.new_stage_async()
        self.stage=self.context.get_stage()
        UsdGeom.SetStageMetersPerUnit(self.stage,1.)
        UsdGeom.SetStageUpAxis(self.stage,UsdGeom.Tokens.z)
        self.original_tcps=self.stage.GetTimeCodesPerSecond()
        self.original_edit=self.stage.GetEditTarget()
        self.layer=Sdf.Layer.CreateAnonymous('NativeRecoveryRoom.usda')
        self.stage.GetSessionLayer().subLayerPaths.insert(0,self.layer.identifier)
        self.stage.SetEditTarget(self.layer)
        self.timeline.stop();self.timeline.commit()
        rep.orchestrator.set_capture_on_play(False)
        source='/World/Excavator/swing_link/MyAiry_front/sensor'
        sensor=self.stage.DefinePrim('/RecoverySensor','OmniLidar')
        sensor.GetReferences().AddReference(self.job['scene'],source)
        if not sensor.IsValid() or sensor.GetAttribute('omni:sensor:Core:instantLidar').Get() is not True:
            raise ContractError('room_sensor','Existing source LiDAR reference did not compose correctly')
        self.pose_op=UsdGeom.Xformable(sensor).MakeMatrixXform()
        self.pose_op.Set(Gf.Matrix4d(1.))
        overrides=[]
        for name,value in [('omni:sensor:tickRate',10.),('omni:sensor:Core:rangeAccuracyM',0.)]:
            attr=sensor.GetAttribute(name)
            before=attr.Get()
            if before is None:raise ContractError('room_schema','Native sensor lacks '+name)
            attr.Set(value)
            overrides.append({'attribute':name,'before':before,'after':value,'scope':'explicit diagnostic room only'})
        self.sensor_overrides=overrides
        entries=[{'id':'MyAiry_front','sensor_id':'lidar/MyAiry_front','prim_path':'/RecoverySensor',
                  'source_prim_path':source,'tick_rate_hz':10.,'parameters':attributes(sensor)}]
        self.registry={'schema_version':3,'recording_id':self.recording_id,'cameras':[],'lidars':entries,
                       'mount_revision':0,'calibration_revision':0,'stage_meters_per_unit':1.,'stage_up_axis':'Z'}
        for axis,coordinate in [(0,10.),(0,-7.),(1,8.),(1,-11.),(2,6.),(2,-4.)]:
            center=[0.,0.,0.];center[axis]=coordinate+math.copysign(.01,coordinate)
            half=[20.,20.,20.];half[axis]=.01
            cube=UsdGeom.Cube.Define(self.stage,'/RecoveryRoom/Wall_%d_%s'%(axis,'plus' if coordinate>0 else 'minus'))
            cube.CreateSizeAttr(2.)
            transform=np.eye(4);transform[:3,:3]=np.diag(half);transform[3,:3]=center
            cube.AddTransformOp().Set(Gf.Matrix4d(transform.tolist()))
            self.room_geometry.append({'axis':axis,'coordinate_m':coordinate,'center_m':center,'halfsize_m':half})
        self.manager.setup_simulation(dt=1./hz)
        RenderingManager.set_dt(1./hz)
        desired={'/rtx/rendermode':'RealTimePathTracing','/rtx/post/dlss/execMode':2,'/rtx/post/aa/op':3,
            '/rtx-transient/dlssg/enabled':False,'/rtx/post/motionblur/enabled':False,
            '/rtx/hydra/supportMultiTickRate':True,'/rtx/rendering/perSensorTickTlas':self.job.get('diagnostics',{}).get('per_sensor_tlas',True),
            '/app/asyncRendering':False,'/renderer/raytracingMotion/enabled':self.job['render'].get('motion_bvh',True),'/rtx/scenedb/maxHistoryTransformCount':64}
        for key,value in desired.items():self.setting(key,value)
        self.callback_ids.append(self.manager.register_callback(self._room_pre,SimulationEvent.PHYSICS_PRE_STEP,order=-100))
        self.callback_ids.append(self.manager.register_callback(self._room_post,SimulationEvent.PHYSICS_POST_STEP,order=100))
        self.timeline.play();self.timeline.commit()
        for _ in range(6):await self.app.next_update_async()
        self.timeline.pause();self.timeline.commit()
        if sensor_products:
            self.backend=ContinuousBackend(self.stage,self.layer,self.registry,lambda e,a:self.on_receipt(e,a),lambda e:self.on_reject(e),self.capability_id,native_trace=True)
        self.render_profile={'schema_version':1,'scope':'minimal pure USD diagnostic sensor; source asset parameters retained except declared noise/tick',
            'effective':{key:self.settings.get(key) for key in desired},'source_scene':self.job['scene'],
            'source_sensor_prim':source,'room_geometry':self.room_geometry,'overrides':overrides}
        rep.orchestrator.set_capture_on_play(sensor_products)
    def _room_pre(self,dt,context=None):
        from pxr import Gf
        try:
            dt=float(dt)
            self.heading+=math.radians(self.profile['yaw_rate_deg_s'])*dt
            self.position[:2]+=self.profile['speed_m_s']*dt*np.array([math.cos(self.heading),math.sin(self.heading)])
            q=[0.,0.,math.sin(self.heading/2),math.cos(self.heading/2)]
            self.pose_op.Set(Gf.Matrix4d(matrix_from_pose(self.position,q).tolist()))
        except Exception as exc:self.error={'code':'room_motion','message':str(exc)}
    def _room_post(self,dt,context=None):
        from pxr import Usd,UsdGeom
        try:
            step=self.manager.get_num_physics_steps()
            matrix=np.array(UsdGeom.Xformable(self.stage.GetPrimAtPath('/RecoverySensor')).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
            p,q=rigid_pose(matrix)
            self.state_revision+=1
            state={'epoch_id':self.epoch_id,'scene_generation':self.scene_generation,'physical_step':step,
                'sim_time_ns':str(source_ns(self.manager.get_simulation_time())),'state_revision':self.state_revision,
                'snapshot_monotonic_ns':str(time.monotonic_ns()),'root':{'position_m':p,'orientation_xyzw':q},
                'sensor_world_matrices_usd':{'lidar/MyAiry_front':matrix.tolist()},
                'diagnostic_actual_scope':'read back USD sensor pose after real physics step; no articulation or contact claim'}
            self.ledger.publish(state);self.on_state(state)
        except Exception as exc:self.error={'code':'room_state','message':str(exc)}
