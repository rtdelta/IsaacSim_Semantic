"""Build a small QA-only stage from the composed new scene, without RTX geometry."""
import json, sys
from pathlib import Path
sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics
root = '/Excavator_Fangshan_05'
source = '/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda'
out = Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer/validation/results/origin03_horizontal')
out.mkdir(parents=True, exist_ok=True)
mask = Usd.StagePopulationMask()
for body in ('track_prim','cab_prim','boom_prim','arm_prim','bucket_prim'):
    mask.Add(root+'/'+body+'/__probe__')
mask.Add(root+'/Joints')
layer = Sdf.Layer.FindOrOpen(source)
sensors = [str(p.path)+'/sensor' for p in layer.GetPrimAtPath(root+'/cab_prim').nameChildren if p.name.startswith('My')]
for p in sensors: mask.Add(p+'/__probe__')
stage = Usd.Stage.OpenMasked(source, mask)
target = out/'tf_validation_fixture.usda'
if target.exists():
    assert target.resolve().parent == out.resolve()
    target.rename(out/('tf_validation_fixture_previous_'+str(target.stat().st_mtime_ns)+'.usda'))
fixture = Usd.Stage.CreateNew(str(target))
UsdGeom.SetStageMetersPerUnit(fixture, 1.)
UsdGeom.SetStageUpAxis(fixture, 'Z')
# Copy composed properties only; no payloads, references, render products or scan buffers.
for p in stage.Traverse():
    if str(p.GetPath()) == '/': continue
    name = str(p.GetPath())
    prim = fixture.DefinePrim(name, 'Xform' if p.GetTypeName() == 'OmniLidar' else p.GetTypeName())
    # Preserve custom Kit/PhysX schemas even when standalone USD has not registered them.
    schemas = p.GetMetadata('apiSchemas')
    if schemas: prim.SetMetadata('apiSchemas', schemas)
    if p.GetCustomData(): prim.SetCustomData(p.GetCustomData())
    for a in p.GetAttributes():
        value = a.Get()
        if value is not None and a.HasAuthoredValueOpinion() and not a.GetName().startswith('omni:'):
            prim.CreateAttribute(a.GetName(), a.GetTypeName(), custom=a.IsCustom()).Set(value)
    for rel in p.GetRelationships():
        prim.CreateRelationship(rel.GetName(), custom=rel.IsCustom()).SetTargets(rel.GetTargets())
scene = UsdPhysics.Scene.Define(fixture, '/PhysicsScene')
scene.CreateGravityMagnitudeAttr(0.)
fixture.SetDefaultPrim(fixture.GetPrimAtPath(root))
fixture.GetRootLayer().Save()
for path in sensors: assert fixture.GetPrimAtPath(path), path
(out/'fixture_sensors.json').write_text(json.dumps([{'id':p.split('/')[-2], 'frame_id':p.split('/')[-2],
    'prim_path':p,'topic':'/lidar/'+p.split('/')[-2]+'/points','record':True} for p in sensors],indent=2))
print(json.dumps({'fixture':str(out/'tf_validation_fixture.usda'),'sensors':len(sensors)}))
