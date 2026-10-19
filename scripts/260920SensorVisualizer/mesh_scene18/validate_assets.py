"""Validate geometry replacement, unchanged scene contract, and in-memory kinematics."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from pxr import Usd,UsdGeom,UsdShade,Gf,Sdf

ROOT=Path('/root/gpufree-data/IsaacSim_Asset')
PROJECT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
WORK=PROJECT/'mesh_scene18'
manifest=json.loads((WORK/'build_manifest.json').read_text())
before=Usd.Stage.Open(manifest['source_scene']);after=Usd.Stage.Open(manifest['scene'])
PARTS=list(manifest['parts'])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def excluded(path):return any(path.startswith('/World/Excavator/'+f+'/Visuals/') for f in PARTS)
def canonical(v):
    if isinstance(v,Sdf.AssetPath):return {'asset':v.resolvedPath or v.path}
    if isinstance(v,dict):return {str(k):canonical(x) for k,x in v.items()}
    if isinstance(v,(str,int,bool,float)) or v is None:return v
    if isinstance(v,(list,tuple)):return [canonical(x) for x in v]
    if type(v).__module__.startswith('pxr.Vt'):
        try:return {'array_type':type(v).__name__,'count':len(v),'sha256':hashlib.sha256(memoryview(v).tobytes()).hexdigest()}
        except TypeError:return [canonical(x) for x in v]
    return str(v)
def signature(prim):
    attrs={}
    for a in prim.GetAttributes():
        if not a.HasAuthoredValueOpinion():continue
        times=a.GetTimeSamples()
        attrs[a.GetName()]={'default':canonical(a.Get()),'samples':{str(t):canonical(a.Get(t)) for t in times},'metadata':canonical({k:v for k,v in a.GetAllMetadata().items() if k not in ('default','timeSamples')})}
    return {'type':prim.GetTypeName(),'active':prim.IsActive(),'instanceable':prim.IsInstanceable(),'schemas':prim.GetAppliedSchemas(),'custom_data':canonical(prim.GetCustomData()),'attributes':attrs,'relationships':{r.GetName():[str(t) for t in r.GetTargets()] for r in prim.GetRelationships()}}
left={str(p.GetPath()):signature(p) for p in before.TraverseAll() if not excluded(str(p.GetPath()))}
right={str(p.GetPath()):signature(p) for p in after.TraverseAll() if not excluded(str(p.GetPath()))}
differences=[p for p in sorted(set(left)|set(right)) if left.get(p)!=right.get(p)]
active_gs=[str(p.GetPath()) for p in after.Traverse() if 'Gaussian' in p.GetTypeName()]
world_errors={};a=UsdGeom.XformCache();b=UsdGeom.XformCache()
for p in before.Traverse():
    path=str(p.GetPath())
    if excluded(path) or not p.IsA(UsdGeom.Xformable):continue
    q=after.GetPrimAtPath(path)
    world_errors[path]=float(np.max(np.abs(np.asarray(a.GetLocalToWorldTransform(p))-np.asarray(b.GetLocalToWorldTransform(q)))))
source=Usd.Stage.Open(manifest['source_mesh']);geometry=[]
for frame,row in manifest['parts'].items():
    src=source.GetPrimAtPath(row['source_prim']);dst=after.GetPrimAtPath(row['target_geometry_path'].replace('/Excavator/','/World/Excavator/',1))
    checks={n:np.array_equal(np.asarray(src.GetAttribute(n).Get()),np.asarray(dst.GetAttribute(n).Get())) for n in ('points','faceVertexCounts','faceVertexIndices','normals','primvars:Col')}
    material,_=UsdShade.MaterialBindingAPI(dst).ComputeBoundMaterial()
    assert material and material.GetPrim().IsValid()
    pts=np.asarray(dst.GetAttribute('points').Get(),dtype=np.float64)
    m=np.asarray(b.GetLocalToWorldTransform(dst));world=pts@m[:3,:3]+m[3,:3]
    geometry.append({'frame':frame,'copied_arrays_equal':checks,'bound_material':str(material.GetPath()),'world_mesh_vertex_bounds':{'min':world.min(axis=0).tolist(),'max':world.max(axis=0).tolist()},'world_mesh_vertex_dimensions_m':(world.max(axis=0)-world.min(axis=0)).tolist()})

sys.path.insert(0,str(PROJECT/'tools'))
from contract_math import load_config,forward,rotation,transform
cfg=load_config();motion=[]
base0=np.asarray(a.GetLocalToWorldTransform(before.GetPrimAtPath('/World/Excavator'))).copy()
for stage in (before,after):stage.SetEditTarget(stage.GetSessionLayer())
poses=[('bind',{},(0,0,0),(0,0,0)),('all_positive',{'swing':15,'boom':15,'arm':15,'bucket':15},(1,-.5,.2),(5,-7,20)),('all_negative',{'swing':-15,'boom':-15,'arm':-15,'bucket':-15},(-.5,.3,-.1),(-5,7,-20))]
for joint in ('boom','arm','bucket'):
    poses.extend([(joint+'_positive',{joint:15},(0,0,0),(0,0,0)),(joint+'_negative',{joint:-15},(0,0,0),(0,0,0))])
for name,angles,translation,rpy in poses:
    base=base0@transform(translation,rotation('Z',rpy[2])@rotation('Y',rpy[1])@rotation('X',rpy[0])).T
    frames=forward(cfg,angles)
    for stage in (before,after):
        for path,m in [('/World/Excavator',base),*[(f'/World/Excavator/{f}',frames[f].T) for f in PARTS]]:
            xf=UsdGeom.Xformable(stage.GetPrimAtPath(path));xf.ClearXformOpOrder();xf.AddTransformOp(opSuffix='meshValidation').Set(Gf.Matrix4d(*m.ravel().tolist()))
    caches=[UsdGeom.XformCache(),UsdGeom.XformCache()];err=0
    for path in world_errors:
        if path.startswith('/World/Excavator'):
            err=max(err,float(np.max(np.abs(np.asarray(caches[0].GetLocalToWorldTransform(before.GetPrimAtPath(path)))-np.asarray(caches[1].GetLocalToWorldTransform(after.GetPrimAtPath(path)))))))
    geometry_err=0
    correction=np.asarray(manifest['coordinate_evidence']['corrected_to_raw'])
    for frame,row in manifest['parts'].items():
        old_visual=before.GetPrimAtPath(f'/World/Excavator/{frame}/Visuals')
        new_mesh=after.GetPrimAtPath(row['target_geometry_path'].replace('/Excavator/','/World/Excavator/',1))
        expected=correction@np.asarray(caches[0].GetLocalToWorldTransform(old_visual))
        geometry_err=max(geometry_err,float(np.max(np.abs(expected-np.asarray(caches[1].GetLocalToWorldTransform(new_mesh))))))
    motion.append({'case':name,'angles_deg':angles,'max_preserved_world_matrix_error':err,'max_mesh_transform_chain_error':geometry_err,'scope':'in-memory prescribed kinematics; no PhysX dynamics claimed'})
hashes=json.loads((Path(manifest['backup_directory'])/'source_hashes.json').read_text())
unchanged=all(sha(p)==h for p,h in hashes.items())
report={'passed':not differences and not active_gs and max(world_errors.values())<1e-10 and unchanged and all(all(r['copied_arrays_equal'].values()) for r in geometry) and all(r['max_mesh_transform_chain_error']<1e-10 for r in motion),'source_files_unchanged':unchanged,'compared_non_geometry_prims':len(left),'non_geometry_differences':differences,'active_gaussian_prims':active_gs,'max_static_world_matrix_error':max(world_errors.values()),'xform_prim_count':len(world_errors),'lidar_count':sum(p.GetTypeName()=='OmniLidar' for p in after.Traverse()),'fisheye_count':sum(p.GetTypeName()=='Camera' and p.GetName().startswith('Fisheye') for p in after.Traverse()),'parts':geometry,'motion_cases':motion,'scene':manifest['scene'],'asset':manifest['asset'],'engine_capture':'pending; separate report'}
(WORK/'validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report));assert report['passed']
