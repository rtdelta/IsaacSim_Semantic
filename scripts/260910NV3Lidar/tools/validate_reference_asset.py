"""Validate a referenced USDA with standard RTX output, without NZ3 loader or NPZ.

The only sensor-authoring operation is USD AddReference. All ray parameters and
the BASIC auxiliary-output preference must come from the asset itself.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import traceback

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--asset',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--smoke',action='store_true')
parser.add_argument('--scene',type=Path,help='Open a previously saved reference scene in a fresh process')
parser.add_argument('--occlusion-control',action='store_true',help='Negative control: temporarily disable rangeOffsetM in the test scene')
parser.add_argument('--preview',action='store_true',help='Capture the referenced housing in Isaac RTX after lidar validation')
args,_=parser.parse_known_args()
args.asset=args.asset.resolve();args.output=args.output.resolve()
args.output.mkdir(parents=True,exist_ok=True)
for name in ('validation.json','failure.txt'):
    (args.output/name).unlink(missing_ok=True)

from isaacsim import SimulationApp
app=SimulationApp(dict(headless=True,multi_gpu=False,fast_shutdown=True,
    renderer='RaytracedLighting',width=640,height=480,
    extra_args=['--/renderer/raytracingMotion/enabled=false',
                '--/rtx/hydra/supportMultiTickRate=false',
                '--/rtx/rendering/perSensorTickTlas=false']))
import numpy as np
import omni.usd
import omni.timeline
import omni.replicator.core as rep
from pxr import Usd,UsdGeom,Sdf,Gf
from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data

TOTAL=480*96
timeline=omni.timeline.get_timeline_interface()


def profile(prim):
    assert prim.GetTypeName()=='OmniLidar'
    assert 'OmniSensorGenericLidarCoreAPI' in prim.GetAppliedSchemas()
    get=lambda n:prim.GetAttribute('omni:sensor:Core:'+n).Get()
    a=np.array(get('emitterState:s001:azimuthDeg'),dtype=np.float64)
    e=np.array(get('emitterState:s001:elevationDeg'),dtype=np.float64)
    assert len(a)==len(e)==TOTAL and get('numberOfEmitters')==TOTAL
    assert get('numLines')==96 and list(get('numRaysPerLine'))==[480]*96
    assert list(get('emitterState:s001:channelId'))==list(range(1,TOTAL+1))
    assert list(prim.GetAttribute('_replicator:rendervar:GenericModelOutput:channels').Get())==['BASIC']
    az,el=np.radians(-a),np.radians(e)
    dirs=np.column_stack((np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)))
    assert len(np.unique(np.round(dirs,7),axis=0))==TOTAL
    digest=hashlib.sha256()
    for attr in sorted(prim.GetAttributes(),key=lambda x:x.GetName()):
        if attr.GetName().startswith('omni:sensor:'):
            digest.update(attr.GetName().encode());digest.update(str(attr.Get()).encode())
    return dirs,digest.hexdigest()


def box(stage,path,center,size):
    cube=UsdGeom.Cube.Define(stage,path);cube.CreateSizeAttr(1.)
    xf=UsdGeom.XformCommonAPI(cube)
    xf.SetTranslate(Gf.Vec3d(*center));xf.SetScale(Gf.Vec3f(*size))


def make_stage():
    omni.usd.get_context().new_stage()
    stage=omni.usd.get_context().get_stage()
    stage.SetDefaultPrim(stage.DefinePrim('/World','Xform'))
    UsdGeom.SetStageMetersPerUnit(stage,1);UsdGeom.SetStageUpAxis(stage,'Z')
    stage.SetTimeCodesPerSecond(60);stage.SetStartTimeCode(0);stage.SetEndTimeCode(600)
    for axis in range(3):
        for sign in (-1,1):
            center=[0.,0.,0.];center[axis]=sign*10.1
            size=[20.4]*3;size[axis]=.2
            box(stage,f'/World/chamber/wall_{axis}_{sign+1}',center,size)
    return stage


def pose(stage,path,position,rotation):
    xf=UsdGeom.XformCommonAPI(stage.GetPrimAtPath(path))
    assert xf.SetTranslate(Gf.Vec3d(*position))
    assert xf.SetRotate(Gf.Vec3f(*rotation))


def reference(stage,path,asset,position,rotation):
    root=stage.DefinePrim(path,'Xform')
    assert root.GetReferences().AddReference(str(asset))
    assert root.GetMetadata('kind')=='component'
    assert root.GetAttribute('nz3:rows').Get()==96
    assert root.GetAttribute('nz3:columns').Get()==480
    geometry=stage.GetPrimAtPath(path+'/geometry')
    assert geometry.GetTypeName()=='Xform'
    meshes=[p for p in Usd.PrimRange(geometry) if p.IsA(UsdGeom.Mesh)]
    if meshes:
        assert len(meshes)==7
        sensor=stage.GetPrimAtPath(path+'/sensor')
        offset=sensor.GetAttribute('omni:sensor:Core:rangeOffsetM').Get()
        assert 0 < offset < sensor.GetAttribute('omni:sensor:Core:nearRangeM').Get()
        root_matrix=UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        inverse=root_matrix.GetInverse()
        xyz=[]
        for p in meshes:
            assert not p.HasAPI('PhysicsCollisionAPI') and not p.HasAPI('PhysicsRigidBodyAPI')
            transform=UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default())*inverse
            xyz.extend([transform.Transform(Gf.Vec3d(v)) for v in UsdGeom.Mesh(p).GetPointsAttr().Get()])
        xyz=np.asarray(xyz)
        assert np.allclose(np.ptp(xyz,axis=0),[.086,.071,.100],atol=1e-6)
        assert np.linalg.norm(xyz,axis=1).max()<offset
    assert len(list(root.GetChildren()))==2
    pose(stage,path,position,rotation)
    return profile(stage.GetPrimAtPath(path+'/sensor'))[1]


def attach(stage,path,label):
    # Standard Replicator data pipeline only. No Lidar() wrapper, checker preload,
    # angle injection, sensor parameter edits, or NZ3-specific runtime functions.
    prim=stage.GetPrimAtPath(path+'/sensor')
    _,before=profile(prim)
    product=rep.create.render_product(str(prim.GetPath()),resolution=(1,1),
                                     name='reference_test_'+label,render_vars=['GenericModelOutput'])
    annot=rep.AnnotatorRegistry.get_annotator('GenericModelOutput',device='cpu',do_array_copy=True)
    annot.attach([product.path])
    assert profile(prim)[1]==before
    return dict(path=path,label=label,product=product,annotator=annot,profile_sha256=before)


def stop(runtimes):
    timeline.stop()
    for rt in runtimes:
        rt['annotator'].detach([rt['product'].path]);rt['product'].destroy()
    for _ in range(5):app.update()


def snapshot(stage,runtimes,with_target):
    for _ in range(35):app.update()
    result={};last_counts={}
    # Other sensors remain visible, and their dark/glancing surfaces need not
    # yield a valid echo. Require every environmental ray; measure all returned
    # housing rays, but do not invent missing echoes on those surfaces.
    required={rt['label']:~ray_truth(stage,rt['path'],with_target)[2] for rt in runtimes}
    accum={rt['label']:dict(xyz=np.zeros((TOTAL,3)),channel_id=np.zeros(TOTAL,dtype=np.uint32),
            seen=np.zeros(TOTAL,dtype=bool),return_counts=[]) for rt in runtimes}
    for step in range(220):
        app.update()
        for rt in runtimes:
            if rt['label'] in result:continue
            raw=rt['annotator'].get_data()
            if isinstance(raw,dict):raw=raw.get('data')
            if raw is None or not len(raw):continue
            g=parse_generic_model_output_data(raw)
            if step in (0,60,150,219):
                missing=np.setdiff1d(np.arange(TOTAL),np.asarray(g.emitterId)) if g.numElements else np.arange(TOTAL)
                last_counts[rt['label']]=dict(elements=int(g.numElements),complete=int(g.scanComplete),
                    missing_emitters=missing[:20].tolist(),timeline_time=timeline.get_current_time(),
                    playing=timeline.is_playing())
                print('NZ3_REFERENCE_BUFFER',step,rt['label'],json.dumps(last_counts[rt['label']]),flush=True)
            if not g.numElements or not g.scanComplete:continue
            xyz=np.column_stack((g.x,g.y,g.z)).copy()
            ids=np.asarray(g.emitterId).astype(int)
            assert ids.min()>=0 and ids.max()<TOTAL and len(np.unique(ids))==len(ids)
            valid=np.isfinite(xyz).all(axis=1)&(np.linalg.norm(xyz,axis=1)>0)
            collected=accum[rt['label']]
            collected['xyz'][ids[valid]]=xyz[valid]
            collected['channel_id'][ids[valid]]=np.asarray(g.channelId)[valid]
            collected['seen'][ids[valid]]=True
            collected['return_counts'].append(int(valid.sum()))
            # Native RTX return filtering can remove a few rays from a frame.
            # At a fixed pose/scene, require every emitter to be observed across
            # frames and report that distinction explicitly rather than hiding it.
            if collected['seen'][required[rt['label']]].all():
                ids=np.flatnonzero(collected['seen'])
                result[rt['label']]=dict(xyz=collected['xyz'][ids],emitter_id=ids,
                    channel_id=collected['channel_id'][ids],frame_id=int(g.frameId),
                    frames_used=len(collected['return_counts']),return_counts=collected['return_counts'])
        if len(result)==len(runtimes):return result
    missing={k:dict(count=int((~v['seen']).sum()),first_ids=np.flatnonzero(~v['seen'])[:20].tolist())
             for k,v in accum.items() if not v['seen'].all()}
    raise RuntimeError(f'Missing emitter coverage after static multi-frame capture: {missing}; last counts: {last_counts}')


def intersection(origin,dirs,lower,upper):
    lo=np.asarray(lower)-origin;hi=np.asarray(upper)-origin
    parallel=np.abs(dirs)<1e-12;safe=np.where(parallel,1.,dirs)
    t1,t2=lo/safe,hi/safe
    near=np.where(parallel,-np.inf,np.minimum(t1,t2)).max(axis=1)
    far=np.where(parallel,np.inf,np.maximum(t1,t2)).min(axis=1)
    outside=(parallel&((lo>0)|(hi<0))).any(axis=1)
    hit=(~outside)&(far>=np.maximum(near,0))
    return np.where(hit,np.where(near>0,near,far),np.inf)


def mesh_intersections(stage,origin,dirs,min_distance):
    """CPU triangle truth for visible housings, including the other sensor's shell.

    Broad-phase bounding boxes reduce triangle tests to the few rays which can
    hit another 10cm housing. Own-shell intersections fall inside rangeOffsetM.
    """
    distance=np.full(len(dirs),np.inf)
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):continue
        mesh=UsdGeom.Mesh(prim)
        if mesh.ComputeVisibility()=='invisible':continue
        m=np.asarray(mesh.ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        vertices=np.asarray(mesh.GetPointsAttr().Get())@m[:3,:3]+m[3,:3]
        if np.linalg.norm(vertices-origin,axis=1).max()<min_distance:continue
        indices=np.flatnonzero(np.isfinite(intersection(origin,dirs,vertices.min(axis=0),vertices.max(axis=0))))
        if not len(indices):continue
        rays=dirs[indices];best=np.full(len(indices),np.inf)
        flat=np.asarray(mesh.GetFaceVertexIndicesAttr().Get());start=0
        for count in mesh.GetFaceVertexCountsAttr().Get():
            face=flat[start:start+count];start+=count
            for j in range(1,count-1):
                a,b,c=vertices[face[[0,j,j+1]]]
                e1,e2=b-a,c-a
                p=np.cross(rays,e2);det=p@e1
                good=np.abs(det)>1e-12;inv=np.where(good,1/np.where(good,det,1),0)
                delta=origin-a;u=(p@delta)*inv
                q=np.cross(delta,e1);v=(rays@q)*inv;t=float(q@e2)*inv
                valid=good&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>min_distance)
                best=np.minimum(best,np.where(valid,t,np.inf))
        distance[indices]=np.minimum(distance[indices],best)
    return distance


def ray_truth(stage,path,with_target):
    prim=stage.GetPrimAtPath(path+'/sensor')
    dirs,_=profile(prim)
    matrix=np.asarray(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    world_dirs=dirs@matrix[:3,:3];origin=matrix[3,:3]
    expected=intersection(origin,world_dirs,[-10]*3,[10]*3)
    if with_target:
        expected=np.minimum(expected,intersection(origin,world_dirs,[4.5,-1,-1],[5.5,1,1]))
    housing=mesh_intersections(stage,origin,world_dirs,float(prim.GetAttribute('omni:sensor:Core:rangeOffsetM').Get() or 0))
    return np.minimum(expected,housing),matrix,housing<expected


def check(stage,rt,frame,phase,with_target):
    prim=stage.GetPrimAtPath(rt['path']+'/sensor')
    dirs,fingerprint=profile(prim)
    assert fingerprint==rt['profile_sha256'],'Rendering changed sensor model parameters'
    ids=frame['emitter_id'].astype(int)
    expected_all,matrix,housing_mask=ray_truth(stage,rt['path'],with_target)
    missing=np.setdiff1d(np.arange(TOTAL),ids)
    assert housing_mask[missing].all(),'An environment ray is missing'
    order=np.argsort(ids);xyz=frame['xyz'][order].astype(float)
    ids=ids[order];dirs=dirs[ids]
    dist=np.linalg.norm(xyz,axis=1);observed=xyz/dist[:,None]
    angular=np.degrees(np.arctan2(np.linalg.norm(np.cross(observed,dirs),axis=1),(observed*dirs).sum(axis=1)))
    origin=matrix[3,:3];expected=expected_all[ids]
    housing_hits=int(housing_mask[ids].sum())
    if housing_mask.any():assert housing_hits>0,'The other housing was not detected'
    error=np.abs(dist-expected)
    assert angular.max()<.005,f'{phase}/{rt["label"]}: direction error {angular.max()}'
    assert error.max()<.02,f'{phase}/{rt["label"]}: world-space range error {error.max()}'
    info=dict(points=len(ids),unique_emitters=len(ids),configured_samples=TOTAL,frame_id=frame['frame_id'],
              capture_mode='single_frame' if frame['frames_used']==1 else 'static_multi_frame_coverage',
              frames_used=frame['frames_used'],per_frame_valid_returns=frame['return_counts'],
              max_angular_error_deg=float(angular.max()),max_range_error_m=float(error.max()),
              world_origin=origin.tolist(),profile_sha256=fingerprint,
              other_housing_hits=housing_hits,
              expected_other_housing_rays=int(housing_mask.sum()),missing_other_housing_emitters=missing.tolist(),
              channel_id_range=[int(frame['channel_id'].min()),int(frame['channel_id'].max())])
    print('NZ3_REFERENCE_CHECK',phase,rt['label'],json.dumps(info),flush=True)
    np.savez_compressed(args.output/f'{phase}_{rt["label"]}.npz',xyz_sensor=xyz,
                        xyz_world=xyz@matrix[:3,:3]+origin,emitter_id=ids,
                        expected_range=expected,observed_range=dist)
    complete_ranges=np.full(TOTAL,np.nan);complete_ranges[ids]=dist
    return info,complete_ranges


def evaluate(stage,runtimes,phase,with_target=False):
    frames=snapshot(stage,runtimes,with_target);info={};ranges={}
    for rt in runtimes:
        info[rt['label']],ranges[rt['label']]=check(stage,rt,frames[rt['label']],phase,with_target)
    return info,ranges


def save_scene(stage,path):
    # Copy only authored World content. This preserves references and transforms
    # while leaving transient render products/graphs in the test process.
    saved=Usd.Stage.CreateNew(str(path))
    assert Sdf.CopySpec(stage.GetRootLayer(),'/World',saved.GetRootLayer(),'/World')
    saved.SetDefaultPrim(saved.GetPrimAtPath('/World'))
    UsdGeom.SetStageMetersPerUnit(saved,1);UsdGeom.SetStageUpAxis(saved,'Z')
    saved.SetTimeCodesPerSecond(60);saved.SetStartTimeCode(0);saved.SetEndTimeCode(600)
    saved.GetRootLayer().Save()


def preview(stage):
    from PIL import Image
    from pxr import UsdLux
    stage.RemovePrim('/World/chamber')
    box(stage,'/World/preview_floor',(0,0,-.052),(2,2,.002))
    floor=stage.GetPrimAtPath('/World/preview_floor')
    UsdGeom.Gprim(floor).CreateDisplayColorAttr([(0.22,0.25,0.29)])
    dome=UsdLux.DomeLight.Define(stage,'/World/preview_dome');dome.CreateIntensityAttr(700)
    light=UsdLux.DistantLight.Define(stage,'/World/preview_key');light.CreateIntensityAttr(1700)
    UsdGeom.XformCommonAPI(light).SetRotate(Gf.Vec3f(-35,-25,20))
    camera=rep.create.camera(position=(.22,.19,.13),look_at=(0,0,-.003),
                             focal_length=45,clipping_range=(.001,100))
    product=rep.create.render_product(camera,(900,900))
    rgb=rep.AnnotatorRegistry.get_annotator('rgb',device='cpu');rgb.attach([product.path])
    timeline.play()
    for _ in range(50):app.update()
    pixels=np.asarray(rgb.get_data())
    assert pixels.shape[:2]==(900,900) and pixels[...,:3].std()>3 and np.percentile(pixels[...,:3],98)>20
    Image.fromarray(pixels[...,:3].astype(np.uint8)).save(args.output/'housing_isaac.png')
    rgb.detach([product.path]);product.destroy()
    timeline.stop()


def main():
    if args.scene:
        assert omni.usd.get_context().open_stage(str(args.scene))
        for _ in range(15):app.update()
        stage=omni.usd.get_context().get_stage()
        paths=[('/World/Robot_A/Sensors/Front','A'),('/World/Robot_B/NZ3Unit','B')]
        for path,_ in paths:assert stage.GetPrimAtPath(path).HasAuthoredReferences()
        runtimes=[attach(stage,path,label) for path,label in paths]
        timeline.play()
        reopened,_=evaluate(stage,runtimes,'reopened',with_target=True)
        stop(runtimes)
        write_report(dict(saved_and_reopened=reopened),'fresh_process_reopen')
        return
    stage=make_stage()
    specs=[('/World/Robot_A/Sensors/Front','A',(0,0,0),(0,0,0))]
    if not args.smoke:specs.append(('/World/Robot_B/NZ3Unit','B',(1.25,-.8,.7),(10,-15,37)))
    fingerprints=[reference(stage,p,args.asset,pos,rot) for p,label,pos,rot in specs]
    assert len(set(fingerprints))==1
    if args.occlusion_control:
        assert args.smoke
        prim=stage.GetPrimAtPath(specs[0][0]+'/sensor')
        assert stage.GetPrimAtPath(specs[0][0]+'/geometry').GetChildren()
        prim.GetAttribute('omni:sensor:Core:rangeOffsetM').Set(0.)
        runtime=attach(stage,specs[0][0],'control');timeline.play()
        for _ in range(40):app.update()
        counts=[]
        for _ in range(30):
            app.update();raw=runtime['annotator'].get_data()
            if isinstance(raw,dict):raw=raw.get('data')
            if raw is None or not len(raw):continue
            g=parse_generic_model_output_data(raw)
            d=np.sqrt(np.asarray(g.x)**2+np.asarray(g.y)**2+np.asarray(g.z)**2)
            counts.append(int((np.isfinite(d)&(d>1)).sum()))
        assert counts and max(counts)<TOTAL*.9,'Control did not demonstrate shell occlusion'
        write_report(dict(range_offset_m=0,frames=len(counts),environment_returns=counts),
                     'negative_control_range_offset_disabled')
        stop([runtime]);return
    runtimes=[attach(stage,p,label) for p,label,_,_ in specs]
    timeline.play()
    baseline,base_ranges=evaluate(stage,runtimes,'reference')
    results=dict(direct_reference=baseline)
    if not args.smoke:
        pose(stage,specs[0][0],(-1.3,1.7,.4),(-12,8,-22))
        box(stage,'/World/test_target',(5,0,0),(1,2,2))
        moved,moved_ranges=evaluate(stage,runtimes,'moved_with_target',with_target=True)
        changed={label:int((np.abs(base_ranges[label]-moved_ranges[label])>.1).sum()) for label in base_ranges}
        assert all(n>100 for n in changed.values())
        results.update(moved_with_target=moved,changed_ranges=changed)
        scene_path=args.output/'reference_scene.usda'
        save_scene(stage,scene_path)
        saved=Usd.Stage.Open(str(scene_path))
        for p,_,_,_ in specs:
            assert profile(saved.GetPrimAtPath(p+'/sensor'))[1]==fingerprints[0]
            assert saved.GetPrimAtPath(p).HasAuthoredReferences()
        results['saved_reference_scene']=str(scene_path)
        relocated=args.output/'relocated_package/NZ3'
        (relocated/'config').mkdir(parents=True,exist_ok=True)
        dependencies=['MyNZ3.usda','config/NZ3_scan.usda']
        if (args.asset.parent/'geometry/NZ3_housing.usda').exists():dependencies.append('geometry/NZ3_housing.usda')
        for rel in dependencies:
            (relocated/rel).parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(args.asset.parent/rel,relocated/rel)
        relocated_stage=Usd.Stage.Open(str(relocated/'MyNZ3.usda'))
        assert profile(relocated_stage.GetPrimAtPath('/NZ3/sensor'))[1]==fingerprints[0]
        results['relocated_package_entry']=str(relocated/'MyNZ3.usda')
    stop(runtimes)
    if args.preview:
        assert args.smoke
        preview(stage)
    write_report(results,'single_reference_smoke' if args.smoke else 'reference_and_pose_acceptance')


def write_report(results,mode):
    housing=(args.asset.parent/'geometry/NZ3_housing.usda').exists()
    report=dict(passed=True,asset=str(args.asset),mode=mode,
                input_dependencies=['MyNZ3.usda','config/NZ3_scan.usda']+(['geometry/NZ3_housing.usda'] if housing else []),
                runtime='USD AddReference + Replicator render product + GenericModelOutput',
                nz3_loader_used=False,calibration_npz_used=False,model_parameters_injected=args.occlusion_control,
                mesh_present=housing,results=results)
    (args.output/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('NZ3_REFERENCE_VALIDATION_PASSED',flush=True)


status=0
try:main()
except Exception:
    status=1;error=traceback.format_exc();print(error,flush=True)
    (args.output/'failure.txt').write_text(error,encoding='utf-8')
finally:app.close(wait_for_replicator=False,exit_code=status)
