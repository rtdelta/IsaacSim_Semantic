"""Create clean, separate geometry overlays without the diagnostic chamber/sensor."""
import json
from pathlib import Path
root = Path(__file__).resolve().parent
source = '/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda'
sensor_path = root / 'sensor_mesh_overlay_v2.usda'
visual_path = root / 'visual_original_overlay_v2.usda'
assert not sensor_path.exists() and not visual_path.exists(), 'Never overwrite existing overlays'
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'fast_shutdown': True, 'limit_cpu_threads': 8,
    'extra_args': ['--/app/settings/loadUserConfig=false', '--/app/settings/persistent=false',
                   '--/renderer/raytracingMotion/enabled=false']})
try:
    from pxr import Sdf, Usd, UsdGeom
    sensor_layer = Sdf.Layer.CreateNew(str(sensor_path))
    sensor_layer.subLayerPaths = [source]
    stage = Usd.Stage.Open(sensor_layer)
    for layer in stage.GetUsedLayers():
        if layer != sensor_layer and not layer.anonymous:
            layer.SetPermissionToEdit(False)
            layer.SetPermissionToSave(False)
    stage.SetEditTarget(sensor_layer)
    excluded = []
    for prim in list(stage.Traverse()):
        if prim and 'particlefield' in prim.GetTypeName().lower():
            excluded.append(str(prim.GetPath()))
            assert prim.SetActive(False)
    selected = []
    for prim in stage.Traverse():
        if prim.GetVariantSets().HasVariantSet('visualization'):
            variant = prim.GetVariantSets().GetVariantSet('visualization')
            selection = next((v for v in ('source_mesh', 'mesh') if v in variant.GetVariantNames()), None)
            if selection:
                assert variant.SetVariantSelection(selection)
                selected.append({'path': str(prim.GetPath()), 'selected': selection})
    remaining = [str(p.GetPath()) for p in stage.Traverse() if 'particlefield' in p.GetTypeName().lower()]
    assert not remaining
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    visible = [str(p.GetPath()) for p in meshes if UsdGeom.Imageable(p).ComputeVisibility() == 'inherited']
    assert len(excluded) == 15 and meshes and visible
    sensor_layer.Save()
    visual_layer = Sdf.Layer.CreateNew(str(visual_path))
    visual_layer.subLayerPaths = [source]
    visual_layer.Save()
    report = {'source': source, 'sensor_overlay': str(sensor_path), 'visual_overlay': str(visual_path),
              'excluded_gaussians': excluded, 'mesh_variant_selected_on': selected,
              'composed_mesh_count': len(meshes), 'visible_mesh_count': len(visible),
              'visible_mesh_paths': visible,
              'scope': 'Clean geometry overlays only. The production graphs/sensors are inherited unchanged. '
                       'Paired-process state synchronization and production sensor accuracy are not validated.'}
    (root / 'isolation_overlay_validation_v2.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'visible_mesh_paths'}, indent=2))
finally:
    app.close(wait_for_replicator=False)
