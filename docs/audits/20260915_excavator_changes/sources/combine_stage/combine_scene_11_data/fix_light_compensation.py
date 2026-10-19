"""Apply the inspected dome-light exclusion to the newly created stage 11 only."""
import json
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Sdf, Gf, Vt
B = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage')
O = B / 'combine_scene_11_data'
before = json.loads((O / 'snapshot_before.json').read_text())
after = json.loads((O / 'snapshot_after.json').read_text())
parent = '/environment_Fangshan_02'
old = Gf.Matrix4d(*[v for row in before['transforms'][parent] for v in row])
new = Gf.Matrix4d(*[v for row in after['transforms'][parent] for v in row])
layer = Sdf.Layer.FindOrOpen(str(B / 'combine_scene_11.usda'))
prim = Sdf.CreatePrimInLayer(layer, parent + '/DomeLight')
name = 'xformOp:transform:stage11KeepLighting'
attr = Sdf.AttributeSpec(prim, name, Sdf.ValueTypeNames.Matrix4d)
attr.default = old * new.GetInverse()
order = Sdf.AttributeSpec(prim, 'xformOpOrder', Sdf.ValueTypeNames.TokenArray, Sdf.VariabilityUniform)
order.default = Vt.TokenArray([name, 'xformOp:translate', 'xformOp:orient', 'xformOp:scale'])
layer.Save()
m = json.loads((O / 'manifest.json').read_text())
m['environment_scaling']['preserved_world_transform_paths'] = [str(prim.path)]
m['environment_scaling']['dome_light_policy'] = 'Parent-space matrix compensation preserves the original world transform and all lighting inputs while the environment parent scales.'
(O / 'manifest.json').write_text(json.dumps(m, indent=2))
report = json.loads((O / 'build_result.json').read_text())
report['environment_scaling'] = m['environment_scaling']
report['scene_sha256'] = hashlib.sha256((B / 'combine_scene_11.usda').read_bytes()).hexdigest()
(O / 'build_result.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'scene_sha256': report['scene_sha256'], 'compensation': [list(row) for row in attr.default]}, indent=2))
