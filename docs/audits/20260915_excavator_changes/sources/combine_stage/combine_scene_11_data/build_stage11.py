"""Author stage 11 only. Run with the installed OpenUSD Python libraries."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Sdf, Gf, Usd, UsdGeom, Vt

B = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage')
SOURCE = B / 'combine_scene_10.usda'
DEST = B / 'combine_scene_11.usda'
OUT = B / 'combine_scene_11_data'
assert not DEST.exists(), 'Refusing to overwrite an existing stage 11'
OUT.mkdir(exist_ok=True)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

paths = list(json.loads((B / 'combine_scene_10_data/source_hashes_before.json').read_text()))
paths.append(str(SOURCE))
before = {p: {'sha256': sha(p), 'size': Path(p).stat().st_size} for p in paths}
(OUT / 'source_hashes_before.json').write_text(json.dumps(before, indent=2))

layer = Sdf.Layer.CreateAnonymous('stage11.usda')
assert layer.ImportFromString(SOURCE.read_text())
R = '/Excavator_Fangshan_05'
root_position = layer.GetAttributeAtPath(R + '.xformOp:translate').default
C = Gf.Vec3d(root_position[0], root_position[1], 0)
K = 2.5

def set_attr(path, name, value_type, value):
    prim = Sdf.CreatePrimInLayer(layer, path)
    attr = prim.attributes.get(name)
    if attr is None:
        attr = Sdf.AttributeSpec(prim, name, value_type)
    attr.default = value

def scale_position(p):
    return C + K * (Gf.Vec3d(*p) - C)

env = '/environment_Fangshan_02'
old_position = layer.GetAttributeAtPath(env + '.xformOp:translate').default
old_scale = layer.GetAttributeAtPath(env + '.xformOp:scale').default
set_attr(env, 'xformOp:translate', Sdf.ValueTypeNames.Double3, scale_position(old_position))
set_attr(env, 'xformOp:scale', Sdf.ValueTypeNames.Float3, Gf.Vec3f(*(K * x for x in old_scale)))

# The referenced grid has a separate SphereLight; keep its parent unscaled.
# Both selected groups have identity source TRS, confirmed from the source USD.
for path in ['/FlatGrid/Environment', '/FlatGrid/GroundPlane']:
    set_attr(path, 'xformOp:translate', Sdf.ValueTypeNames.Double3, scale_position((0, 0, 0)))
    set_attr(path, 'xformOp:scale', Sdf.ValueTypeNames.Float3, Gf.Vec3f(K))

# Preserve the world transform of the dome light inside the environment payload.
def environment_matrix(position, scale):
    temporary = Usd.Stage.CreateInMemory()
    xf = UsdGeom.Xform.Define(temporary, '/Root')
    xf.AddTranslateOp().Set(position)
    xf.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(layer.GetAttributeAtPath(env + '.xformOp:orient').default)
    xf.AddScaleOp(UsdGeom.XformOp.PrecisionFloat).Set(scale)
    return xf.GetLocalTransformation()

compensation = environment_matrix(old_position, old_scale) * environment_matrix(scale_position(old_position), Gf.Vec3f(K)).GetInverse()
light_path = env + '/DomeLight'
compensation_op = 'xformOp:transform:stage11KeepLighting'
set_attr(light_path, compensation_op, Sdf.ValueTypeNames.Matrix4d, compensation)
set_attr(light_path, 'xformOpOrder', Sdf.ValueTypeNames.TokenArray, Vt.TokenArray([compensation_op, 'xformOp:translate', 'xformOp:orient', 'xformOp:scale']))
layer.GetAttributeAtPath(light_path + '.xformOpOrder').variability = Sdf.VariabilityUniform

# Keep the existing overview path so no hierarchy or camera bindings change.
camera = '/World/Stage10Overview'
camera_old = layer.GetAttributeAtPath(camera + '.xformOp:transform').default
camera_new = Gf.Matrix4d(camera_old)
camera_new.SetTranslateOnly(scale_position(camera_old.ExtractTranslation()))
set_attr(camera, 'xformOp:transform', Sdf.ValueTypeNames.Matrix4d, camera_new)

meta = layer.customLayerData
meta['omni_layer']['authoring_layer'] = './combine_scene_11.usda'
meta['stage11'] = {
    'sourceScene': './combine_scene_10.usda',
    'environmentScaleFactor': K,
    'worldPivotMeters': C,
    'scope': 'Fangshan environment, grid visual ground and collision plane; Cube, excavator, sensors and lights unchanged',
}
layer.customLayerData = meta
assert layer.Export(str(DEST))

manifest = json.loads((B / 'combine_scene_10_data/manifest.json').read_text())
manifest.update(scene=str(DEST), source_scene=str(SOURCE), source_count=len(before))
manifest['environment_scaling'] = {
    'factor': K, 'world_pivot_m': list(C),
    'point_rule': 'p11 = C + 2.5 * (p10 - C)',
    'scaled_subtrees': [env, '/FlatGrid/Environment', '/FlatGrid/GroundPlane'],
    'unchanged_subtrees': ['/World/Cube', R, '/Environment', '/FlatGrid/SphereLight', '/FlatGrid/Looks', '/PhysicsScene', '/Render', '/World/Stage10SensorPipeline', '/World/Stage10BaseAnchor'],
    'preserved_world_transform_paths': [light_path],
    'dome_light_policy': 'Parent-space matrix compensation preserves the original world transform and all lighting inputs while the environment parent scales.',
    'overview_path': camera,
    'overview_position_before_m': list(camera_old.ExtractTranslation()),
    'overview_position_after_m': list(camera_new.ExtractTranslation()),
    'environment_root_translation_before_m': list(old_position),
    'environment_root_translation_after_m': list(scale_position(old_position)),
    'ground_group_translation_after_m': list(scale_position((0, 0, 0))),
    'grid_note': 'Finite visual plane grows from 100 x 100 m to 250 x 250 m at Z=0; the infinite collision plane remains the same world plane. Grid material inputs are unchanged.',
}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))

helper = (B / 'combine_scene_10_data/capture_sensors.py').read_text()
helper = helper.replace('stage10', 'stage11').replace('Stage10', 'Stage11').replace('scene_10', 'scene_11')
(OUT / 'capture_sensors.py').write_text(helper)
desktop = (B / 'combine_scene_10_data/IsaacSim_Stage10.desktop').read_text()
desktop = desktop.replace('Stage 10', 'Stage 11').replace('scene_10', 'scene_11')
(OUT / 'IsaacSim_Stage11.desktop').write_text(desktop)
(OUT / 'IsaacSim_Stage11.desktop').chmod(0o755)
changed = [p for p, row in before.items() if sha(p) != row['sha256']]
report = {'scene': str(DEST), 'scene_sha256': sha(DEST), 'source_files_checked': len(before), 'changed_source_files': changed, 'environment_scaling': manifest['environment_scaling'], 'passed': not changed}
(OUT / 'build_result.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
