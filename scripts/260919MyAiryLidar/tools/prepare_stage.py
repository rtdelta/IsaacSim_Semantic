"""Create a sibling combine stage; run inside Isaac's USD environment."""
import hashlib
import json
from pathlib import Path
from pxr import Sdf, Usd, UsdGeom


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(source, destination, asset, report_path):
    source, destination, asset = map(Path, (source, destination, asset))
    assert source.parent == destination.parent, 'Keep relative asset paths anchored in the same directory'
    assert not destination.exists(), 'Refusing to overwrite an existing scene'
    layer = Sdf.Layer.FindOrOpen(str(source))
    old_asset = '../sensor_set/lidar_set/Rotator360_90/MyOS0.usda'
    new_asset = '../sensor_set/lidar_set/MyAiry/MyAiry.usda'
    source_text = layer.ExportToString()
    assert source_text.count('@'+old_asset+'@') == 7
    # Exact model prefix substitution also updates persisted graph/relationship
    # targets, Render Product names and UI path strings in this root layer.
    text = source_text.replace('@'+old_asset+'@', '@'+new_asset+'@').replace('MyOS0_', 'MyAiry_')
    text = text.replace('./'+source.name, './'+destination.name)
    result = Sdf.Layer.CreateNew(str(destination))
    assert result.ImportFromString(text)
    mapping = []
    def visit(path):
        spec = result.GetPrimAtPath(path)
        if spec and spec.name.startswith('MyAiry_') and any(p.assetPath == new_asset for p in spec.payloadList.GetAppliedItems()):
            mapping.append(dict(old_path=str(path).replace('MyAiry_', 'MyOS0_'), new_path=str(path)))
            if 'os0_mesh' in spec.nameChildren:
                del spec.nameChildren['os0_mesh']
    result.Traverse(Sdf.Path.absoluteRootPath, visit)
    assert len(mapping) == 7
    result.customLayerData = dict(result.customLayerData, myairyConversion=dict(
        source=str(source), sourceSha256=sha(source), asset=str(asset), assetSha256=sha(asset),
        policy='Replace seven MyOS0 payloads; retain mount transforms and six MyNZ3 instances'))
    result.Save()
    report = dict(source=str(source), scene=str(destination), source_sha256=sha(source),
                  scene_sha256=sha(destination), asset=str(asset), asset_sha256=sha(asset), mapping=mapping)
    Path(report_path).write_text(json.dumps(report, indent=2)+'\n')
    return report


def verify(stage, conversion):
    import numpy as np
    original = Sdf.Layer.FindOrOpen(conversion['source'])
    report = []
    for item in conversion['mapping']:
        old = original.GetPrimAtPath(item['old_path'])
        root = stage.GetPrimAtPath(item['new_path'])
        sensor = stage.GetPrimAtPath(item['new_path']+'/sensor')
        assert sensor and sensor.GetTypeName() == 'OmniLidar'
        for name, attr in old.attributes.items():
            if name.startswith('xformOp'):
                assert root.GetAttribute(name).Get() == attr.default, (str(root.GetPath()), name)
        get = lambda name: sensor.GetAttribute('omni:sensor:Core:'+name).Get()
        assert get('scanType') == 'SOLID_STATE' and get('instantLidar')
        assert get('numberOfEmitters') == 85632 and get('rangeOffsetM') == 0
        parent_m = UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        sensor_m = UsdGeom.Xformable(sensor).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        np.testing.assert_allclose(np.asarray(parent_m), np.asarray(sensor_m), atol=1e-9)
        report.append(dict(**item, world_matrix_row_vectors=np.asarray(sensor_m).tolist()))
    sensors = [p for p in stage.Traverse() if p.GetTypeName() == 'OmniLidar']
    assert len(sensors) == 13
    assert sum('MyAiry_' in str(p.GetPath()) for p in sensors) == 7
    assert sum('MyNZ3_' in str(p.GetPath()) for p in sensors) == 6
    assert 'MyOS0_' not in stage.GetRootLayer().ExportToString()
    for prim in stage.Traverse():
        for relationship in prim.GetRelationships():
            for path in relationship.GetTargets():
                if 'MyAiry_' in str(path):
                    assert stage.GetPrimAtPath(path.GetPrimPath()), str(path)
    return report
