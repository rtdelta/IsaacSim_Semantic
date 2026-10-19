"""Read-only comparison of the deployed Fangshan and CET200 assets."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdUtils

BASE = Path('/root/gpufree-data/IsaacSim_Asset')
FILES = {
    'fangshan': BASE/'excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_05_origin03.usda',
    'cet200': BASE/'excavator_module_set/CET200/usd/CET200.usda',
}


def value(v):
    if v is None or isinstance(v, (str,bool,int)): return v
    if isinstance(v,float): return v if math.isfinite(v) else str(v)
    if isinstance(v,Sdf.Path): return str(v)
    try: return [value(x) for x in v]
    except TypeError:return str(v)


out={}
for key,path in FILES.items():
    s=Usd.Stage.Open(str(path))
    root=s.GetDefaultPrim()
    variants={name:{'selected':root.GetVariantSet(name).GetVariantSelection(),
                    'options':root.GetVariantSet(name).GetVariantNames()} for name in root.GetVariantSets().GetNames()}
    if key=='fangshan':
        s.SetEditTarget(s.GetSessionLayer())
        root.GetVariantSet('visualization').SetVariantSelection('3dgs')
    prims=list(Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()))
    data={'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
          'default_prim':str(root.GetPath()),'meters_per_unit':UsdGeom.GetStageMetersPerUnit(s),
          'up_axis':UsdGeom.GetStageUpAxis(s),'variants':variants,
          'prim_types':dict(Counter(p.GetTypeName() for p in prims)),
          'root_children':[str(p.GetPath()) for p in root.GetChildren()],
          'rigid_bodies':[],'joints':[],'colliders':[],'splat_data':[],
          'articulation_roots':[str(p.GetPath()) for p in s.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]}
    total_points=0
    total_faces=0
    for p in prims:
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            names=['physics:mass','physics:centerOfMass','physics:diagonalInertia','physics:principalAxes',
                   'physics:kinematicEnabled','physics:rigidBodyEnabled','physxRigidBody:disableGravity']
            data['rigid_bodies'].append({'path':str(p.GetPath()),'attributes':{n:value(p.GetAttribute(n).Get()) for n in names if p.GetAttribute(n)}})
        if p.IsA(UsdPhysics.Joint):
            data['joints'].append({'path':str(p.GetPath()),'type':p.GetTypeName(),
                'attributes':{a.GetName():value(a.Get()) for a in p.GetAttributes() if a.GetName().startswith(('physics:','drive:','physxJoint:'))},
                'relationships':{r.GetName():value(r.GetTargets()) for r in p.GetRelationships() if r.GetName().startswith('physics:')}})
        if p.HasAPI(UsdPhysics.CollisionAPI):
            data['colliders'].append({'path':str(p.GetPath()),'type':p.GetTypeName(),
                'enabled':value(p.GetAttribute('physics:collisionEnabled').Get()),
                'approximation':value(p.GetAttribute('physics:approximation').Get())})
        if p.IsA(UsdGeom.Mesh):
            a=UsdGeom.Mesh(p).GetPointsAttr().Get();f=UsdGeom.Mesh(p).GetFaceVertexCountsAttr().Get()
            total_points+=len(a) if a is not None else 0
            total_faces+=len(f) if f is not None else 0
        if any(x in p.GetTypeName().lower() for x in ['gaussian','splat']):
            attrs={a.GetName():{'type':str(a.GetTypeName()),'size':len(a.Get()) if a.Get() is not None and hasattr(a.Get(),'__len__') else None} for a in p.GetAttributes() if a.GetName() not in ['points','primvars:shCoefficients']}
            a=p.GetAttribute('points')
            data['splat_data'].append({'path':str(p.GetPath()),'points_count':len(a.Get()) if a and a.Get() is not None else None,'attrs':attrs})
    data['mesh_vertices']=total_points;data['mesh_faces']=total_faces
    layers,assets,unresolved=UsdUtils.ComputeAllDependencies(str(path))
    deps=[Path(x.identifier) for x in layers]+[Path(x) for x in assets]
    data['dependencies']={'layer_count':len(layers),'asset_count':len(assets),'unresolved':unresolved,
                          'total_bytes':sum(p.stat().st_size for p in set(deps) if p.is_file())}
    data['total_authored_mass_kg']=sum(x['attributes'].get('physics:mass',0) or 0 for x in data['rigid_bodies'])
    data['material_count']=sum(p.GetTypeName()=='Material' for p in prims)
    out[key]=data

scene_path=BASE/'combine_stage/combine_scene_11_origin03.usda'
scene_layer=Sdf.Layer.FindOrOpen(str(scene_path))
out['fangshan_scene']={'file':str(scene_path),'sha256':hashlib.sha256(scene_path.read_bytes()).hexdigest(),
                       'layer_text':scene_layer.ExportToString()[:65000]}
out['cet200_source_joints']=json.loads((BASE/'excavator_module_set/CET200/reports/source_joints.json').read_text())
out['fangshan_kinematics']=json.loads((BASE/'excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_05_origin03_data/kinematics_origin03.json').read_text()) if (BASE/'excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_05_origin03_data/kinematics_origin03.json').exists() else None
print(json.dumps(out,indent=2,ensure_ascii=True))
