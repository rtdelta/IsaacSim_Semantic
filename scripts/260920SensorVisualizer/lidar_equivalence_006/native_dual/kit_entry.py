"""Independent native capture: persistent official helpers and engine updates.

No imports from Sensor Visualizer versions, custom tickets, mmap transport or
custom sensor Writers. File logging contains timing/configuration, never arrays.
"""
import asyncio,ctypes,hashlib,json,os,time,traceback
import sys
from pathlib import Path

OUT=Path(os.environ['NATIVE_BASELINE_OUTPUT'])
SPEC=json.loads(Path(os.environ['NATIVE_BASELINE_SPEC']).read_text())
sys.path.insert(0,str(Path(__file__).resolve().parent))

def write(name,value):
    p=OUT/name;tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,default=str));tmp.replace(p)

def event(name,**values):
    with (OUT/'engine_events.jsonl').open('a') as f:
        f.write(json.dumps({'event':name,'monotonic_ns':time.monotonic_ns(),
                            'utc_ns':time.time_ns(),**values},default=str)+'\n')

class Markers:
    def __init__(self):
        self.lib=None
        if SPEC.get('trace'):
            self.lib=ctypes.CDLL('/usr/local/cuda/lib64/libnvToolsExt.so.1')
            self.lib.nvtxRangePushA.argtypes=[ctypes.c_char_p]
            self.lib.nvtxMarkA.argtypes=[ctypes.c_char_p]
    def begin(self):
        if self.lib:
            self.lib.nvtxRangePushA(b'NATIVE_CAPTURE_WINDOW')
            self.lib.nvtxMarkA(('NATIVE_SYNC '+str(time.monotonic_ns())).encode())
    def end(self):
        if self.lib:
            self.lib.nvtxMarkA(('NATIVE_SYNC '+str(time.monotonic_ns())).encode())
            self.lib.nvtxRangePop()

def discover(stage):
    from pxr import UsdGeom
    sensors=[]
    for p in stage.Traverse():
        path=str(p.GetPath())
        if not path.startswith(SPEC['robot']+'/'):continue
        if p.GetTypeName()=='OmniLidar':
            sensors.append({'kind':'lidar','id':p.GetParent().GetName(),'prim_path':path,
                'frame_id':p.GetParent().GetName(),'topic':'/lidar/'+p.GetParent().GetName()+'/points',
                'size':[300,300],
                'parameters':{a.GetName():a.Get() for a in p.GetAttributes() if any(s in a.GetName() for s in
                 ['instantLidar','scanType','scanRateBaseHz','tickRate','outputFrameOfReference','nearRangeM','farRangeM'])}})
        elif p.IsA(UsdGeom.Camera) and p.GetAttribute('omni:lensdistortion:model').Get()=='opencvFisheye':
            sid=p.GetName().removeprefix('Fisheye').lower().replace('rear','back')
            key='omni:lensdistortion:opencvFisheye:'
            sensors.append({'kind':'camera','id':sid,'prim_path':path,
                'frame_id':'fisheye_'+sid+'_optical','topic':'/camera/fisheye_'+sid+'/image_raw',
                'info_topic':'/camera/fisheye_'+sid+'/camera_info',
                'size':list(p.GetAttribute(key+'imageSize').Get()),
                'exposure_attributes':{a.GetName():a.Get() for a in p.GetAttributes() if 'exposure' in a.GetName().lower()},
                'calibration':{n:p.GetAttribute(key+n).Get() for n in ['fx','fy','cx','cy','k1','k2','k3','k4']}})
    sensors.sort(key=lambda s:(s['kind'],s['id']))
    for kind,key in [('lidar','expected_lidars'),('camera','expected_cameras')]:
        if sum(s['kind']==kind for s in sensors)!=SPEC[key]:raise RuntimeError('Sensor count mismatch: '+kind)
    if len({s['topic'] for s in sensors})!=len(sensors):raise RuntimeError('Duplicate native topic')
    return sensors

def native_graph(stage,sensors,products,root_frame_path,articulation_path):
    import omni.graph.core as og
    from pxr import Gf,Sdf,UsdGeom
    k=og.Controller.Keys
    nodes=[('Tick','omni.graph.action.OnPlaybackTick'),
           ('Time','isaacsim.core.nodes.IsaacReadSimulationTime'),
           ('Clock','isaacsim.ros2.bridge.ROS2PublishClock'),
           ('SensorTF','isaacsim.ros2.bridge.ROS2PublishTransformTree'),
           ('RootTF','isaacsim.ros2.bridge.ROS2PublishTransformTree'),
           ('Joints','isaacsim.ros2.bridge.ROS2PublishJointState')]
    con=[('Tick.outputs:tick',n+'.inputs:execIn') for n in ['Clock','SensorTF','RootTF','Joints']]
    con += [('Time.outputs:simulationTime',n+'.inputs:timeStamp') for n in ['Clock','SensorTF','RootTF','Joints']]
    vals=[('Time.inputs:resetOnStop',False),('Clock.inputs:topicName','/clock'),
          ('SensorTF.inputs:topicName','/tf'),('RootTF.inputs:topicName','/tf'),
          ('SensorTF.inputs:parentPrim',[Sdf.Path(root_frame_path)]),
          ('RootTF.inputs:targetPrims',[Sdf.Path(root_frame_path)]),
          ('Joints.inputs:topicName','/joint_states'),('Joints.inputs:targetPrim',[Sdf.Path(articulation_path)])]
    targets=[]
    for i,(s,rp) in enumerate(zip(sensors,products)):
        p=stage.GetPrimAtPath(s['prim_path'])
        if s['kind']=='camera':
            # USD camera axes: right/up/-Z; ROS optical: right/down/+Z.
            optical=UsdGeom.Xform.Define(stage,s['prim_path']+'/NativeOpticalFrame')
            optical.AddOrientOp().Set(Gf.Quatf(0,Gf.Vec3f(1,0,0)))
            frameprim=optical.GetPrim();s['tf_prim_path']=str(frameprim.GetPath())
        else:frameprim=p;s['tf_prim_path']=s['prim_path']
        frameprim.CreateAttribute('isaac:nameOverride',Sdf.ValueTypeNames.String).Set(s['frame_id'])
        targets.append(frameprim.GetPath())
        name='Sensor'+str(i)
        nodes.append((name,'isaacsim.ros2.bridge.ROS2CameraHelper' if s['kind']=='camera' else
                      'isaacsim.ros2.bridge.ROS2RtxLidarHelper'))
        con.append(('Tick.outputs:tick',name+'.inputs:execIn'))
        vals.extend([(name+'.inputs:renderProductPath',rp.path),(name+'.inputs:topicName',s['topic']),
          (name+'.inputs:frameId',s['frame_id']),(name+'.inputs:queueSize',64),
          (name+'.inputs:resetSimulationTimeOnStop',False),(name+'.inputs:useSystemTime',False),
          (name+'.inputs:type','rgb' if s['kind']=='camera' else 'point_cloud')])
        if s['kind']=='lidar':vals.append((name+'.inputs:fullScan',False)) # ignored by installed 6.0; suppress obsolete warning
        if s['kind']=='camera':
            info=name+'Info';nodes.append((info,'isaacsim.ros2.bridge.ROS2CameraInfoHelper'))
            con.append(('Tick.outputs:tick',info+'.inputs:execIn'))
            vals.extend([(info+'.inputs:renderProductPath',rp.path),(info+'.inputs:frameId',s['frame_id']),
              (info+'.inputs:topicName',s['info_topic']),(info+'.inputs:resetSimulationTimeOnStop',False)])
    vals.append(('SensorTF.inputs:targetPrims',targets))
    og.Controller.edit({'graph_path':'/NativeCaptureBaselineGraph','evaluator_name':'execution'},
                      {k.CREATE_NODES:nodes,k.CONNECT:con,k.SET_VALUES:vals})
    return {'nodes':nodes,'targets':[str(p) for p in targets],'root_frame_path':root_frame_path,
            'note':'Helper-generated SDGPipeline performs native sensor processing and ROS publication.'}

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

async def main():
    import omni.kit.app,omni.usd,omni.timeline,carb.settings
    import omni.replicator.core as rep
    from pxr import Gf,Sdf,Usd,UsdGeom,UsdPhysics,PhysxSchema,UsdRender
    from isaacsim.core.simulation_manager import SimulationManager
    app=omni.kit.app.get_app();ctx=omni.usd.get_context();timeline=omni.timeline.get_timeline_interface()
    (OUT/'kit.pid').write_text(str(os.getpid()));event('process_entry');code=1
    try:
        settings=carb.settings.get_settings()
        app.get_extension_manager().set_extension_enabled_immediate('isaacsim.ros2.bridge',True)
        await app.next_update_async()
        scene=Path(SPEC['scene']);before_hash=hashlib.sha256(scene.read_bytes()).hexdigest()
        if before_hash!=SPEC['scene_sha256']:raise RuntimeError('Root USD differs from approved baseline')
        event('stage_open_begin')
        ok=await ctx.open_stage_async(str(scene))
        if isinstance(ok,tuple) and not ok[0]:raise RuntimeError('USD open failed: '+str(ok))
        deadline=time.monotonic()+120
        while ctx.get_stage_loading_status()[2]:
            if time.monotonic()>deadline:raise TimeoutError('USD loading timeout')
            await app.next_update_async()
        stage=ctx.get_stage();timeline.stop();await app.next_update_async()
        stage.SetEditTarget(stage.GetSessionLayer())
        # Native helpers attach Replicator writers: capture-on-play must stay
        # enabled for their SDG pipelines to execute during ordinary Kit updates.
        rep.orchestrator.set_capture_on_play(SPEC.get('capture_on_play_during_groups',False) if SPEC.get('experiment') else True)
        sensors=discover(stage)
        from experiment import align_scene,configure_quality,run_groups
        alignment=align_scene(stage,sensors)
        event('stage_loaded',sensors=len(sensors),usd_pending=list(ctx.get_stage_loading_status()))
        for name,value in {'/rtx/rendermode':SPEC['render_mode'],'/rtx/post/dlss/execMode':SPEC['dlss_mode'],
          '/rtx/post/aa/op':SPEC['aa_mode'],'/rtx-transient/dlssg/enabled':False,
          '/app/runLoops/main/rateLimitEnabled':False,'/app/player/useFixedTimeStepping':True}.items():settings.set(name,value)
        configure_quality(settings,SPEC)
        for p in stage.Traverse():
            if p.IsA(UsdRender.Settings):
                for name,val in {'omni:rtx:rendermode':SPEC['render_mode'],'omni:rtx:post:dlss:execMode':'quality'}.items():
                    attr=p.GetAttribute(name)
                    if attr:attr.Set(val)
        # Prescribed-motion baseline matches previous gravity/collision/drive policy.
        robot=stage.GetPrimAtPath(SPEC['robot'])
        roots=[p for p in Usd.PrimRange(robot) if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        if len(roots)!=1:raise RuntimeError('Expected one native articulation root')
        root=roots[0]
        for p in Usd.PrimRange(robot):
            if p.HasAPI(UsdPhysics.RigidBodyAPI):PhysxSchema.PhysxRigidBodyAPI.Apply(p).CreateDisableGravityAttr().Set(True)
            if p.HasAPI(UsdPhysics.CollisionAPI):UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr().Set(False)
            if p.IsA(UsdPhysics.RevoluteJoint) and p.HasAPI(UsdPhysics.DriveAPI,'angular'):
                drive=UsdPhysics.DriveAPI(p,'angular');drive.CreateStiffnessAttr().Set(0);drive.CreateDampingAttr().Set(0);drive.CreateMaxForceAttr().Set(0)
        reference_in_root=UsdGeom.Xformable(robot).ComputeLocalToWorldTransform(Usd.TimeCode.Default())*UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).GetInverse()
        ref=UsdGeom.Xform.Define(stage,str(root.GetPath())+'/NativeReferenceFrame')
        ref.AddTransformOp().Set(reference_in_root)
        ref.GetPrim().CreateAttribute('isaac:nameOverride',Sdf.ValueTypeNames.String).Set('swing_coordinate')
        products=[];annotators=[]
        for s in sensors:
            with Usd.EditContext(stage,stage.GetSessionLayer()):
                rp=rep.create.render_product(s['prim_path'],s['size'],name='NativeBaseline_'+s['id'],force_new=True)
            products.append(rp);event('native_product_created',sensor=s['id'],path=rp.path)
            if SPEC['mode']=='render':
                ann=rep.AnnotatorRegistry.get_annotator('rgb' if s['kind']=='camera' else 'IsaacExtractRTXSensorPointCloud',device='cuda',do_array_copy=False)
                ann.attach([rp.path]);annotators.append(ann)
        graph=None
        if SPEC['mode']!='render':graph=native_graph(stage,sensors,products,str(ref.GetPath()),str(root.GetPath()))
        try:
            import omni.kit.viewport.utility
            viewport=omni.kit.viewport.utility.get_active_viewport()
            if viewport:viewport.updates_enabled=False
        except ImportError:pass
        timeline.set_target_framerate(SPEC['physics_hz'])
        SimulationManager.setup_simulation(dt=1/SPEC['physics_hz'],device='cpu')
        timeline.play();timeline.commit()
        trajectory=None;art=None
        if SPEC.get('trajectory'):
            from isaacsim.core.experimental.prims import Articulation
            import numpy as np
            trajectory=[json.loads(line) for line in Path(SPEC['trajectory']).read_text().splitlines() if line.strip()]
            art=Articulation(str(root.GetPath()),reset_xform_op_properties=False)
            for _ in range(6):await app.next_update_async()
            initial=art.get_dof_positions().numpy().copy()
            names=list(trajectory[0]['joints_deg']);indices=art.get_dof_indices(names).numpy().astype(int).ravel().tolist()
            def apply_state(index):
                state=trajectory[min(index,len(trajectory)-1)]
                q=state['quaternion_xyzw'];m=Gf.Matrix4d(1);m.SetRotate(Gf.Quatd(q[3],Gf.Vec3d(*q[:3])));m.SetTranslateOnly(Gf.Vec3d(*state['position_world_m']))
                root_world=reference_in_root.GetInverse()*m;quat=root_world.ExtractRotationQuat().GetNormalized()
                art.set_world_poses(positions=[list(root_world.ExtractTranslation())],orientations=[[quat.GetReal(),*quat.GetImaginary()]])
                pos=initial.copy()
                for name,idx in zip(names,indices):pos[0,idx]=np.deg2rad(state['joints_deg'][name])
                art.set_dof_positions(pos);art.set_dof_velocities(np.zeros_like(pos))
                art.set_velocities(linear_velocities=[[0,0,0]],angular_velocities=[[0,0,0]])
                SimulationManager.get_physics_simulation_view().update_articulations_kinematic()
                import omni.physx
                omni.physx.get_physx_interface().update_transformations(False,True,False,False)
            apply_state(0)
        write('sensor_manifest.json',{'sensors':sensors,'graph':graph,'scene':str(scene),'root_sha256':before_hash,
           'alignment':alignment,
           'used_layers':[{'path':l.realPath,'container_path':l.realPath.split('[',1)[0],'sha256_container':hashlib.sha256(Path(l.realPath.split('[',1)[0]).read_bytes()).hexdigest()}
                          for l in stage.GetUsedLayers() if l.realPath and Path(l.realPath.split('[',1)[0]).is_file()],
           'settings':{n:settings.get(n) for n in ['/rtx/rendermode','/rtx/post/dlss/execMode','/rtx/post/aa/op',
             '/rtx/hydra/supportMultiTickRate','/rtx/rendering/perSensorTickTlas','/renderer/raytracingMotion/enabled',
             '/rtx/post/histogram/enabled','/rtx/post/tonemap/op','/rtx/post/tonemap/filmIso',
             '/rtx/post/tonemap/cameraShutter','/rtx/post/tonemap/fNumber']},
           'differences':['Images use native lossless sensor_msgs/Image instead of project PNG CompressedImage.',
             'This run freezes simulation time at each trajectory pose and renders 16+2 RT2 subframes.',
             'Native TF plus JointState carry poses; project group index/root PoseStamped/camera PoseStamped/horizontal frame are not fabricated.']})
        event('warmup_begin')
        if SPEC.get('experiment') and SPEC.get('freeze_method')!='autoupdate':
            timeline.pause();timeline.commit()
            await asyncio.wait_for(rep.orchestrator.step_async(delta_time=0.,pause_timeline=SPEC.get('pause_after_step',True),wait_for_render=True,rt_subframes=SPEC['warmup_frames']),timeout=90.)
            timeline.pause();timeline.commit()
        else:
            for _ in range(SPEC['warmup_frames']):await app.next_update_async()
        event('warmup_end',native_time=SimulationManager.get_simulation_time())
        markers=Markers();markers.begin();event('measurement_begin',native_time=SimulationManager.get_simulation_time())
        wall_start=time.monotonic_ns();sim_start=SimulationManager.get_simulation_time();frame_rows=[]
        if SPEC.get('experiment')=='continuous_pt':
            from continuous import run_continuous
            frame_rows=await run_continuous(app,ctx,timeline,stage,sensors,products,art,initial,indices,names,settings,OUT,SPEC,event)
        elif SPEC.get('experiment'):
            frame_rows=await run_groups(app,ctx,timeline,stage,sensors,products,art,initial,indices,names,settings,OUT,SPEC,event,apply_trajectory_state=apply_state)
        for i in range(0 if SPEC.get('experiment') else SPEC['measure_frames']):
            if (OUT/'stop.request').exists():break
            if trajectory and SPEC['motion']=='moving':apply_state(i//max(1,round(SPEC['physics_hz']/10)))
            t=time.monotonic_ns();cpu=time.thread_time_ns()
            if SPEC['schedule']=='frozen':
                timeline.pause();timeline.commit()
                await rep.orchestrator.step_async(delta_time=0.0,pause_timeline=True,wait_for_render=True,rt_subframes=SPEC['subframes'])
            else:await app.next_update_async()
            frame_rows.append({'frame':i,'start_ns':t,'end_ns':time.monotonic_ns(),
                               'inclusive_thread_cpu_ns':time.thread_time_ns()-cpu,'native_time_s':SimulationManager.get_simulation_time()})
        sim_end=SimulationManager.get_simulation_time();wall_ns=time.monotonic_ns()-wall_start
        event('measurement_end',native_time=sim_end,frames=len(frame_rows));markers.end()
        (OUT/'frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in frame_rows))
        # Native publication is one update behind acquisition. Flush at the
        # end only, with the last pose held; never add per-sample own scheduling.
        drain_frames=2 if SPEC['schedule']=='continuous' and not SPEC.get('experiment') else 0
        event('publication_drain_begin',frames=drain_frames)
        for _ in range(drain_frames):await app.next_update_async()
        event('publication_drain_end',native_time=SimulationManager.get_simulation_time())
        timeline.pause();timeline.commit()
        pose_cache=UsdGeom.XformCache()
        reference_world=pose_cache.GetLocalToWorldTransform(ref.GetPrim())
        final_poses={s['frame_id']:[list(row) for row in pose_cache.GetLocalToWorldTransform(stage.GetPrimAtPath(s['tf_prim_path'] if graph else s['prim_path']))] for s in sensors}
        final_poses['swing_coordinate']=[list(row) for row in reference_world]
        write('final_poses.json',final_poses)
        def components(m):
            q=m.ExtractRotationQuat().GetNormalized()
            return {'translation':list(m.ExtractTranslation()),'quaternion_xyzw':[*q.GetImaginary(),q.GetReal()]}
        transforms={'swing_coordinate':components(reference_world)}
        for s in sensors:
            m=Gf.Matrix4d(final_poses[s['frame_id']])
            transforms[s['frame_id']]=components(m*reference_world.GetInverse())
        write('expected_final_transforms.json',transforms)
        drain_s=None
        if SPEC.get('experiment') and SPEC.get('experiment')!='continuous_pt':
            event('explicit_capture_drain_begin');drain_start=time.monotonic()
            await asyncio.wait_for(rep.orchestrator.stop_async(),timeout=30.)
            drain_s=time.monotonic()-drain_start;event('explicit_capture_drain_end',wall_s=drain_s)
        root_unchanged=hashlib.sha256(scene.read_bytes()).hexdigest()==before_hash
        if len(frame_rows)!=SPEC['measure_frames']:raise RuntimeError('Requested group count was not completed')
        write('engine_result.json',{'ok':True,'frames':len(frame_rows),'wall_s':wall_ns/1e9,
             'engine_updates_per_wall_second':len(frame_rows)/(wall_ns/1e9),'simulation_start_s':sim_start,
             'simulation_end_s':sim_end,'real_time_factor':(sim_end-sim_start)/(wall_ns/1e9),
             'publication_tail_updates':drain_frames,'native_final_drain_s':drain_s,
             'root_usd_unchanged':root_unchanged,'schedule':SPEC['schedule'],'trace':SPEC['trace']})
        if not root_unchanged:raise RuntimeError('Root USD changed')
        event('capture_complete');code=0
    except BaseException as exc:
        traceback.print_exc();write('engine_error.json',{'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()});event('failed',error=str(exc))
    finally:
        event('shutdown_begin');timeline.stop()
        # Publisher/graph cleanup belongs to Kit, once at shutdown.
        app.post_quit(code)

task=asyncio.ensure_future(main())
