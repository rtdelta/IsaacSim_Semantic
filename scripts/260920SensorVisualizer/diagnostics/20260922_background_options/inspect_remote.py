import json
import os
from pathlib import Path
import subprocess
import sys

code = r'''
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from pxr import Sdf, Usd, UsdGeom
folder = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage')
result = {}
for name in ['combine_scene_15_surround_fisheye.usda', 'combine_scene_16_terrain_fisheye.usda']:
    path = folder/name
    stage = Usd.Stage.Open(str(path), load=Usd.Stage.LoadNone)
    rows = []
    for prim in Usd.PrimRange.Stage(stage, Usd.PrimAllPrimsPredicate):
        p = str(prim.GetPath())
        if p.startswith(('/World/Excavator', '/Render')): continue
        if p.count('/') > 5: continue
        row = dict(path=p, type=prim.GetTypeName(), active=prim.IsActive(), loaded=prim.IsLoaded(),
                   visibility=str(prim.GetAttribute('visibility').Get()), payload=prim.HasPayload())
        if prim.IsA(UsdGeom.Imageable): row['computed_visibility'] = str(UsdGeom.Imageable(prim).ComputeVisibility())
        row['arcs'] = [{'layer': s.layer.identifier, 'references': str(s.referenceList), 'payloads': str(s.payloadList)}
                       for s in prim.GetPrimStack() if s.referenceList or s.payloadList]
        row['asset_attributes'] = {a.GetName(): str(a.Get()) for a in prim.GetAttributes()
                                    if a.GetTypeName() in (Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray)}
        rows.append(row)
    result[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), root_text=path.read_text() if name.startswith('combine_scene_16') else None,
                       sublayers=list(stage.GetRootLayer().subLayerPaths), prims=rows,
                       composition_errors=[str(e) for e in stage.GetCompositionErrors()])
print(json.dumps(result))
'''
libs = sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))[-1]
env = dict(os.environ)
env['LD_LIBRARY_PATH'] = str(next(libs.rglob('libusd_tf.so')).parent)+':/root/isaacsim/kit/lib'
result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(libs)], env=env,
                        capture_output=True, text=True, timeout=40)
print(json.dumps(dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)))
raise SystemExit(result.returncode)
