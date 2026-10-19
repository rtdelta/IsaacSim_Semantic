"""Read deployed USD facts for the handoff; never author to the source stages."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf

ROOT = Path('/root/gpufree-data/IsaacSim_Asset')
ASSET = ROOT/'excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda'
SOURCE = ROOT/'excavator_module_set/Sim_Fangshan_02/waji_mesh_corrected.usdc'
SCENE = ROOT/'combine_stage/combine_scene_18_terrain_fisheye_mesh.usda'
RAW = ROOT/'excavator_module_set/sim_Fangshan_01/mechanic_parts_set/mesh_parts/拆分成五部分的mesh.usd'
PARTS = {'track_link':'track','swing_link':'operator_cab','boom_link':'boom','arm_link':'small_arm','bucket_link':'bucket_only_full_teeth'}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mat(m): return [list(row) for row in m]
def val(v):
    if isinstance(v, (str,bool,int,float)) or v is None: return v
    if isinstance(v, dict): return {k:val(x) for k,x in v.items()}
    if isinstance(v, Sdf.AssetPath): return {'authored':v.path,'resolved':v.resolvedPath}
    if isinstance(v, (Gf.Quatd,Gf.Quatf,Gf.Quath)): return [v.GetReal(),*list(v.GetImaginary())]
    try: return [val(x) for x in v]
    except TypeError: return str(v)
def bounds(points, matrix):
    m=np.asarray(matrix); xyz=points@m[:3,:3]+m[3,:3]
    return {'min':xyz.min(0).tolist(),'max':xyz.max(0).tolist(),'dimensions':np.ptp(xyz,axis=0).tolist()}

source=Usd.Stage.Open(str(SOURCE)); asset=Usd.Stage.Open(str(ASSET)); scene=Usd.Stage.Open(str(SCENE))
cache=UsdGeom.XformCache()
report={'python':sys.version,'usd':list(Usd.GetVersion()),'numpy':np.__version__,
    'source':{'path':str(SOURCE),'sha256':sha(SOURCE),'bytes':SOURCE.stat().st_size,
              'meters_per_unit':UsdGeom.GetStageMetersPerUnit(source),'up_axis':str(UsdGeom.GetStageUpAxis(source))},
    'asset':{'path':str(ASSET),'sha256':sha(ASSET)},'scene':{'path':str(SCENE),'sha256':sha(SCENE)},'parts':{},'joints':{}}
for frame,part in PARTS.items():
    path=f'/root/{part}_mesh/{part}_mesh'; prim=source.GetPrimAtPath(path)
    mesh=UsdGeom.Mesh(prim); pts=np.asarray(mesh.GetPointsAttr().Get(),dtype=np.float64)
    attributes={}
    for a in prim.GetAttributes():
        if not a.HasAuthoredValueOpinion(): continue
        v=a.Get(); arr=np.asarray(v)
        entry={'usd_type':str(a.GetTypeName()),'metadata':val({k:v for k,v in a.GetAllMetadata().items() if k not in ('default','timeSamples','allowedTokens')})}
        if arr.ndim and arr.dtype.kind in 'biuf':
            entry.update(shape=list(arr.shape),dtype=str(arr.dtype),sha256=hashlib.sha256(arr.tobytes()).hexdigest())
        else: entry['value']=val(v)
        attributes[a.GetName()]=entry
    body=asset.GetPrimAtPath('/Excavator/'+frame)
    geom=f'/Excavator/{frame}/Visuals/MeshAlignment/Geometry/Mesh'
    report['parts'][frame]={'source_prim':path,'source_local_matrix_row':mat(mesh.GetLocalTransformation()),
        'source_world_matrix_row':mat(cache.GetLocalToWorldTransform(prim)),
        'source_attributes':attributes,'source_normals_interpolation':str(mesh.GetNormalsInterpolation()),
        'vertices':len(pts),'faces':len(mesh.GetFaceVertexCountsAttr().Get()),
        'body_bind_matrix_row':mat(UsdGeom.Xformable(body).GetLocalTransformation()),
        'visual_matrix_row':mat(UsdGeom.Xformable(asset.GetPrimAtPath(f'/Excavator/{frame}/Visuals')).GetLocalTransformation()),
        'corrected_to_raw_row':mat(UsdGeom.Xformable(asset.GetPrimAtPath(f'/Excavator/{frame}/Visuals/MeshAlignment')).GetLocalTransformation()),
        'bounds_source_numeric':bounds(pts,np.eye(4)),
        'bounds_body_m':bounds(pts,cache.ComputeRelativeTransform(asset.GetPrimAtPath(geom),body)[0]),
        'bounds_asset_m':bounds(pts,cache.GetLocalToWorldTransform(asset.GetPrimAtPath(geom))),
        'bounds_scene_m':bounds(pts,cache.GetLocalToWorldTransform(scene.GetPrimAtPath(geom.replace('/Excavator/','/World/Excavator/',1))))}
for joint in asset.GetPrimAtPath('/Excavator/Joints').GetChildren():
    report['joints'][joint.GetName()]={'type':joint.GetTypeName(),
        'attributes':{a.GetName():{'type':str(a.GetTypeName()),'value':val(a.Get())} for a in joint.GetAttributes() if a.HasAuthoredValueOpinion()},
        'relationships':{r.GetName():[str(p) for p in r.GetTargets()] for r in joint.GetRelationships() if r.HasAuthoredTargets()}}
report['scene']['root_world_matrix_row']=mat(cache.GetLocalToWorldTransform(scene.GetPrimAtPath('/World/Excavator')))
report['scene']['root_authored_attributes']={a.GetName():{'type':str(a.GetTypeName()),'value':val(a.Get())} for a in scene.GetPrimAtPath('/World/Excavator').GetAttributes() if a.HasAuthoredValueOpinion()}
report['scene']['dependencies']=[{'path':l.realPath,'container_path':l.realPath.split('[',1)[0],'sha256_container':sha(l.realPath.split('[',1)[0]),'bytes_container':Path(l.realPath.split('[',1)[0]).stat().st_size} for l in sorted(scene.GetUsedLayers(),key=lambda l:l.identifier) if l.realPath]
report['scene']['sensors']=[]
for prim in scene.Traverse():
    if prim.GetTypeName() not in ('OmniLidar','Camera') or not str(prim.GetPath()).startswith('/World/Excavator/'): continue
    report['scene']['sensors'].append({'path':str(prim.GetPath()),'type':prim.GetTypeName(),
        'local_matrix_row':mat(UsdGeom.Xformable(prim).GetLocalTransformation()),
        'body_relative_matrix_row':mat(cache.ComputeRelativeTransform(prim,scene.GetPrimAtPath('/World/Excavator/swing_link'))[0]),
        'world_matrix_row':mat(cache.GetLocalToWorldTransform(prim))})
if RAW.exists():
    raw=Usd.Stage.Open(str(RAW))
    report['earlier_unsplit_raw']={'path':str(RAW),'sha256':sha(RAW),'bytes':RAW.stat().st_size,
        'meters_per_unit':UsdGeom.GetStageMetersPerUnit(raw),'up_axis':str(UsdGeom.GetStageUpAxis(raw)),
        'meshes':[str(p.GetPath()) for p in raw.Traverse() if p.IsA(UsdGeom.Mesh)]}
print(json.dumps(report,ensure_ascii=False))
