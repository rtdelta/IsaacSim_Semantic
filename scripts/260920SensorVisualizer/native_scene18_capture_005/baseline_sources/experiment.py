"""Official frozen capture experiment; observation is separate from render timing.

No old runtime imports, no fabricated sensor stamps, no custom MCAP serializer.
PNG extraction is diagnostic evidence, not the official ROS data path.
"""
import asyncio,hashlib,json,time,math,ctypes
from pathlib import Path

def align_scene(stage,sensors):
    from pxr import Usd,UsdRender,UsdGeom,UsdLux
    paths={s['prim_path'] for s in sensors};nodes=[];products=[];dome=[]
    selected='/environment_Fangshan_02/DomeLight'
    if not stage.GetPrimAtPath(selected):raise RuntimeError('Expected baseline DomeLight missing')
    for p in list(stage.Traverse()):
        attr=p.GetAttribute('node:type')
        if attr and attr.Get()=='isaacsim.core.nodes.IsaacCreateRenderProduct':
            targets=p.GetRelationship('inputs:cameraPrim').GetTargets()
            if targets and str(targets[0]) in paths:
                p.GetAttribute('inputs:enabled').Set(False);nodes.append(str(p.GetPath()))
        if p.IsA(UsdRender.Product):
            targets=UsdRender.Product(p).GetCameraRel().GetTargets()
            if targets and str(targets[0]) in paths and any(not x.layer.anonymous for x in p.GetPrimStack()):products.append(str(p.GetPath()))
        if p.IsA(UsdLux.DomeLight):
            attr=UsdGeom.Imageable(p).GetVisibilityAttr();before=attr.Get()
            attr.Set('inherited' if str(p.GetPath())==selected else 'invisible')
            dome.append({'path':str(p.GetPath()),'before':before,'after':attr.Get()})
    for p in list(stage.Traverse()):
        if p.IsA(UsdRender.Settings):
            rel=UsdRender.Settings(p).GetProductsRel();rel.SetTargets([t for t in rel.GetTargets() if str(t) not in products])
    for path in products:stage.OverridePrim(path).SetActive(False)
    return {'dome':dome,'selected_dome':selected,'suspended_initializers':nodes,'suspended_scene_products':products,'scope':'Session only'}

def configure_quality(settings,spec):
    settings.set('/omni/replicator/RTSubframes',1)
    settings.set('/omni/replicator/captureMotionBlur',False)
    settings.set('/rtx/post/motionblur/enabled',False)
    for name,value in {'/rtx/pathtracing/spp':spec.get('pt_spp',32),
        '/rtx/pathtracing/totalSpp':spec.get('pt_total_spp',64),
        '/rtx/pathtracing/maxBounces':spec.get('pt_bounces',8),
        '/rtx/pathtracing/adaptiveSampling/enabled':False,
        '/rtx/pathtracing/optixDenoiser/enabled':True,
        '/rtx/pathtracing/optixDenoiser/temporalMode/enabled':False,
        '/rtx/resetPtAccumOnAnimTimeChange':spec.get('reset_pt_per_frame',False)}.items():settings.set(name,value)

def inspect_native_graph(stage,products,out,bypass=False):
    """Observe installed OG edges; optional diagnostic removes physics gates only.

    All converters/extractors/publishers remain NVIDIA nodes. This variation is
    labelled explicitly and is NOT claimed to be an unchanged Helper pipeline.
    """
    owned=[Path(rp.path).name for rp in products];rows=[];gates={}
    prims=list(stage.Traverse())
    for p in prims:
        attr=p.GetAttribute('node:type');kind=attr.Get() if attr else None
        if not kind or not (any(n in str(p.GetPath()) for n in owned) or str(kind).endswith('WriterSyncGate') or str(kind).endswith('OnFrame')):continue
        edges={a.GetName():[str(s) for s in a.GetConnections()] for a in p.GetAttributes() if a.GetConnections()}
        scalars={a.GetName():a.Get() for a in p.GetAttributes() if a.GetName().startswith('inputs:') and str(a.GetTypeName()) in ('bool','int','uint','int64','uint64','double','float','token','string')}
        rows.append({'path':str(p.GetPath()),'type':kind,'connections':edges,'scalar_inputs':scalars,'execution_attributes':[a.GetName() for a in p.GetAttributes() if 'execution' in str(a.GetTypeName()).lower()]})
        if str(kind).endswith('IsaacSimulationGate'):
            sources=p.GetAttribute('inputs:execIn').GetConnections()
            if sources:gates[str(p.GetPath())+'.outputs:execOut']=sources
    changes=[]
    if bypass:
        if not gates:raise RuntimeError('No owned native simulation gates found for diagnostic')
        for p in prims:
            for a in p.GetAttributes():
                sources=a.GetConnections();revised=[]
                for source in sources:revised.extend(gates.get(str(source),[source]))
                if revised!=sources:a.SetConnections(revised);changes.append(str(a.GetPath()))
    if bypass:
        # Diagnostic only: attach native point publisher to the extractor's
        # completion edge, avoiding a physics-reference WriterSyncGate. No data
        # pointer or header input is replaced or manufactured.
        for p in prims:
            kind=p.GetAttribute('node:type')
            if not kind or not str(kind.Get()).endswith('ROS2PublishPointCloud') or not any(n in str(p.GetPath()) for n in owned):continue
            source=p.GetAttribute('inputs:dataPtr').GetConnections()
            if not source:continue
            extractor=stage.GetPrimAtPath(source[0].GetPrimPath())
            execution=next((a for a in extractor.GetAttributes() if a.GetName().startswith('outputs:exec')),None)
            if execution:
                p.GetAttribute('inputs:execIn').SetConnections([execution.GetPath()]);changes.append(str(p.GetPath())+'.inputs:execIn')
    (out/'native_pipeline_graph.json').write_text(json.dumps({'nodes':rows,'gate_sources':{k:[str(x) for x in v] for k,v in gates.items()},'diagnostic_bypass':bypass,'rewired_edges':changes},indent=2))
    return changes

def cases(spec):
    kind=spec['experiment'];out=[]
    if kind=='comparison_static':return [dict(name='comparison_'+spec['render_mode'],renderer=spec['render_mode'],warm=16 if spec['render_mode']=='RealTimePathTracing' else 1,formal=2 if spec['render_mode']=='RealTimePathTracing' else 1,repeat=spec.get('repeat',0),pose='static',**({'total_spp':spec['pt_total_spp']} if spec['render_mode']=='PathTracing' else {})) for _ in range(spec['measure_frames'])]
    if kind=='reference':return [{'name':'reference_rt16','renderer':'RealTimePathTracing','warm':16,'formal':2,'repeat':spec.get('reference_repeat',0),'pose':'static'} for _ in range(6)]
    if kind in ('smoke','control'):return [{'name':'frozen_'+kind,'renderer':'RealTimePathTracing','warm':2,'formal':2,'repeat':0,'pose':p} for p in ('static','joint','mount')]
    if kind=='rt':
        for repeat in range(3):
            for warm in ((1,2,4,8,16) if repeat%2==0 else (16,8,4,2,1)):
                for pose in ('static','joint','mount'):out.append({'name':'rt_'+str(warm),'renderer':'RealTimePathTracing','warm':warm,'formal':2,'repeat':repeat,'pose':pose})
    elif kind=='pt':
        for repeat in range(3):
            for spp in ((64,256,512,1024) if repeat%2==0 else (1024,512,256,64)):
                out.append({'name':'pt_'+str(spp),'renderer':'PathTracing','total_spp':spp,'warm':1,'formal':1,'repeat':repeat,'pose':'mount'})
    elif kind=='trace':return [{'name':'rt16_trace','renderer':'RealTimePathTracing','warm':16,'formal':2,'repeat':0,'pose':p} for p in ('static','joint','mount')]+[{'name':'pt1024_trace','renderer':'PathTracing','total_spp':1024,'warm':1,'formal':1,'repeat':0,'pose':'mount'}]
    else:raise ValueError('Unknown experiment '+kind)
    return out

async def run_groups(app,ctx,timeline,stage,sensors,products,art,initial,indices,names,settings,out,spec,event):
    import numpy as np
    import omni.replicator.core as rep
    import omni.graph.core as og
    from pxr import UsdGeom,Gf,UsdRender
    from isaacsim.core.simulation_manager import SimulationManager
    camera_indices=[i for i,s in enumerate(sensors) if s['kind']=='camera']
    observers={}
    lidar_observers={}
    for i in camera_indices:
        ann=rep.AnnotatorRegistry.get_annotator('rgb');ann.attach([products[i].path])
        params=rep.AnnotatorRegistry.get_annotator('CameraParams');params.attach([products[i].path])
        observers[i]=(ann,params)
    for i,s in enumerate(sensors):
        if s['kind']=='lidar':
            ann=rep.AnnotatorRegistry.get_annotator('IsaacExtractRTXSensorPointCloud',device='cpu',do_array_copy=True);ann.attach([products[i].path]);lidar_observers[i]=ann
    # Disabling implicit Play/Pause orchestration leaves explicit step ownership.
    rep.orchestrator.set_capture_on_play(spec.get('capture_on_play_during_groups',False))
    auto_freeze=spec.get('freeze_method')=='autoupdate'
    if not auto_freeze:timeline.pause();timeline.commit()
    # Initialized directly in explicit mode: there is no running continuous
    # scenario to stop here. Stopping at every boundary recreates SDK resources.
    event('explicit_capture_ownership',capture_on_play=settings.get('/omni/replicator/captureOnPlay'))
    changes=inspect_native_graph(stage,products,out,spec.get('bypass_native_simulation_gate',False))
    event('native_graph_inspected',diagnostic_rewired_edges=len(changes))
    front=next(s for s in sensors if s['kind']=='camera' and s['id']=='front')
    prim=stage.GetPrimAtPath(front['prim_path']);x=UsdGeom.Xformable(prim)
    mount=x.AddRotateYOp(opSuffix='NC002MountAdjustment');mount.Set(0)
    lidar_front=next(s for s in sensors if s['id']=='MyAiry_front')
    lidar_mount=UsdGeom.Xformable(stage.GetPrimAtPath(lidar_front['prim_path'])).AddRotateYOp(opSuffix='NC002MountAdjustment');lidar_mount.Set(0)
    poses=[('static',0.,0.),('joint',15.,0.),('mount',0.,45.)]
    rows=[];matrix=cases(spec);write_dir=out/'quality_images';write_dir.mkdir(exist_ok=True)
    nvtx=None
    if spec.get('trace'):
        nvtx=ctypes.CDLL('/usr/local/cuda/lib64/libnvToolsExt.so.1');nvtx.nvtxRangePushA.argtypes=[ctypes.c_char_p]
    for index,case in enumerate(matrix):
        if (out/'stop.request').exists():break
        event('group_begin',group=index,case=case)
        start=time.monotonic_ns();cpu=time.thread_time_ns()
        if spec.get('gate_products_between_groups',True):
            for rp in products:rp.hydra_texture.set_updates_enabled(False)
        # Advance only BETWEEN snapshots; render history intentionally sees a jump.
        timeline.set_auto_update(True);timeline.play();timeline.commit()
        pos=initial.copy();joint=15. if case['pose']=='joint' else 0.
        for idx in indices:pos[0,idx]=np.deg2rad(joint)
        art.set_dof_positions(pos);art.set_dof_velocities(np.zeros_like(pos));mount.Set(45. if case['pose']=='mount' else 0.)
        lidar_mount.Set(45. if case['pose']=='mount' else 0.)
        for _ in range(6):await app.next_update_async()
        if auto_freeze:timeline.set_auto_update(False)
        else:timeline.pause()
        timeline.commit();stamp=SimulationManager.get_simulation_time()
        cache=UsdGeom.XformCache();before={s['frame_id']:[list(r) for r in cache.GetLocalToWorldTransform(stage.GetPrimAtPath(s['prim_path']))] for s in sensors}
        actual_joints=art.get_dof_positions().numpy().copy()
        reference=next(p for p in stage.Traverse() if p.GetName()=='NativeReferenceFrame')
        reference_world=cache.GetLocalToWorldTransform(reference);expected_tf={}
        for s in sensors:
            m=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(s['tf_prim_path']))*reference_world.GetInverse()
            q=m.ExtractRotationQuat().GetNormalized();expected_tf[s['frame_id']]={'parent':'swing_coordinate','translation':list(m.ExtractTranslation()),'quaternion_xyzw':[*q.GetImaginary(),q.GetReal()]}
        q=reference_world.ExtractRotationQuat().GetNormalized();expected_tf['swing_coordinate']={'parent':'world','translation':list(reference_world.ExtractTranslation()),'quaternion_xyzw':[*q.GetImaginary(),q.GetReal()]}
        settings.set('/rtx/rendermode',case['renderer'])
        if 'total_spp' in case:settings.set('/rtx/pathtracing/totalSpp',case['total_spp'])
        for p in stage.Traverse():
            if p.IsA(UsdRender.Settings):
                a=p.GetAttribute('omni:rtx:rendermode')
                if a:a.Set(case['renderer'])
        for rp in products:rp.hydra_texture.set_updates_enabled(True)
        # Native reset bounds accumulation to this pose, never to a prior image.
        ctx.reset_renderer_accumulation()
        advance_done=time.monotonic_ns();event('group_render_begin',group=index,native_time=stamp)
        if nvtx:nvtx.nvtxRangePushA(f'NC002_GROUP_{index}_WARM'.encode())
        await rep.orchestrator.step_async(delta_time=0.,pause_timeline=spec.get('pause_after_step',True),wait_for_render=True,rt_subframes=case['warm'])
        if nvtx:nvtx.nvtxRangePop();nvtx.nvtxRangePushA(f'NC002_GROUP_{index}_FORMAL'.encode())
        warm_done=time.monotonic_ns()
        await rep.orchestrator.step_async(delta_time=0.,pause_timeline=spec.get('pause_after_step',True),wait_for_render=True,rt_subframes=case['formal'])
        if nvtx:nvtx.nvtxRangePop();nvtx.nvtxRangePushA(f'NC002_GROUP_{index}_EVIDENCE'.encode())
        if not auto_freeze:timeline.pause();timeline.commit()
        render_done=time.monotonic_ns();render_cpu_done=time.thread_time_ns();after_time=SimulationManager.get_simulation_time()
        if abs(after_time-stamp)>1e-7:raise RuntimeError('Simulation time advanced during frozen rendering')
        after=UsdGeom.XformCache();pose_error=max(np.max(np.abs(np.asarray(before[s['frame_id']])-np.asarray(after.GetLocalToWorldTransform(stage.GetPrimAtPath(s['prim_path']))))) for s in sensors)
        if pose_error>2e-6:raise RuntimeError('USD pose moved during snapshot')
        evidence={};lidar_evidence={}
        # Evidence read and PNG encode are separately timed, outside renderer timing.
        for i,(ann,params) in observers.items():
            rgb=np.asarray(ann.get_data());cp=params.get_data()
            if rgb.size==0:raise RuntimeError('Empty native RGB '+sensors[i]['id'])
            rgb=np.ascontiguousarray(rgb[:,:,:3]);view=np.asarray(cp['cameraViewTransform']).reshape(4,4)
            rendered=np.linalg.inv(view);want=np.asarray(before[sensors[i]['frame_id']]);err=float(np.max(np.abs(rendered-want)))
            image=write_dir/(f'{index:03d}_'+sensors[i]['id']+'.png')
            from PIL import Image
            if spec.get('export_quality_images',True):Image.fromarray(rgb).save(image)
            evidence[sensors[i]['topic']]={'sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),'image':str(image.relative_to(out)),
                'camera_pose_max_abs_error':err,'shape':list(rgb.shape)}
        for i,ann in lidar_observers.items():
            try:
                cloud=ann.get_data();value=cloud['data'];xyz=value.numpy() if hasattr(value,'numpy') else np.asarray(value)
                xyz=np.ascontiguousarray(xyz,dtype='<f4').reshape(-1,3);rendered=np.asarray(cloud['info']['transform']).reshape(4,4)
                lidar_evidence[sensors[i]['topic']]={'points':len(xyz),'sha256_xyz':hashlib.sha256(xyz.tobytes()).hexdigest(),
                    'render_pose_max_abs_error':float(np.max(np.abs(rendered-np.asarray(before[sensors[i]['frame_id']])))),'info_keys':sorted(cloud['info'])}
            except Exception as exc:
                lidar_evidence[sensors[i]['topic']]={'observation_error':type(exc).__name__+': '+str(exc)}
                event('lidar_observation_failed',group=index,topic=sensors[i]['topic'],error=lidar_evidence[sensors[i]['topic']]['observation_error'])
        read_done=time.monotonic_ns()
        if nvtx:nvtx.nvtxRangePop()
        row={'frame':index,'group':index,'case':case,'start_ns':start,'end_ns':render_done,
            'inclusive_thread_cpu_ns':render_cpu_done-cpu,'evidence_thread_cpu_ns':time.thread_time_ns()-render_cpu_done,'advance_s':(advance_done-start)/1e9,
            'warm_s':(warm_done-advance_done)/1e9,'formal_s':(render_done-warm_done)/1e9,
            'ready_scope_s':(render_done-start)/1e9,'evidence_s':(read_done-render_done)/1e9,
            'payload_observed_scope_s':(read_done-start)/1e9,'quality_png_exported':spec.get('export_quality_images',True),
            'native_time_s':stamp,'native_time_after_s':after_time,'pose_change_error':float(pose_error),
            'freeze_method':spec.get('freeze_method','pause'),'timeline_playing_while_render':auto_freeze,
            'gate_products_between_groups':spec.get('gate_products_between_groups',True),'diagnostic_native_gate_bypass':spec.get('bypass_native_simulation_gate',False),
            'joints_rad':{n:float(actual_joints[0,j]) for n,j in zip(names,indices)},'images':evidence,'lidars':lidar_evidence,'expected_tf':expected_tf,
            'requested_pt_total_spp':case.get('total_spp'),
            'sdk_nominal_pt_subframes_per_call':math.ceil(case['total_spp']/spec.get('pt_spp',32)) if 'total_spp' in case else None,
            'pt_budget_semantics':'Per-renderer accumulation ceiling; two SDK calls may reset/reuse accumulation. Not claimed as exact executed rays.',
            'settings':{k:settings.get(k) for k in ('/rtx/rendermode','/rtx/pathtracing/spp','/rtx/pathtracing/totalSpp','/rtx/pathtracing/maxBounces','/rtx/pathtracing/adaptiveSampling/enabled','/rtx/pathtracing/optixDenoiser/enabled','/rtx/post/histogram/enabled','/rtx/post/tonemap/op','/rtx/post/tonemap/filmIso','/rtx/post/tonemap/cameraShutter','/rtx/post/tonemap/fNumber')}}
        rows.append(row)
        with (out/'groups.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        event('group_complete',group=index,case=case,native_time=stamp,render_s=(render_done-advance_done)/1e9,evidence_s=row['evidence_s'])
    return rows
