"""Transfer donor sensors by shared raw geometry into the contract articulation.

Matrices in reports/NumPy use column vectors; Gf matrices use row vectors.
No source asset, source scene, or sensor asset is edited.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import numpy as np

from usd_environment import initialize
initialize()
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics
from contract_math import ROOT, points, sha256, write_json


def matrix(stage, path):
    return np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(str(path)))).T


def gf(m):
    return Gf.Matrix4d(*np.asarray(m).T.ravel().tolist())


def rigid(m):
    u, singular, vt = np.linalg.svd(m[:3, :3])
    assert np.max(np.abs(singular - 1)) < 1e-5, ('Unexpected scale', singular)
    r = u @ vt
    assert np.linalg.det(r) > 0, 'Reflected mount frame'
    out = m.copy(); out[:3, :3] = r
    return out


def set_pose(prim, m):
    m = rigid(m)
    for attr in list(prim.GetAttributes()):
        if attr.GetName().startswith('xformOp:') or attr.GetName() == 'xformOpOrder':
            prim.RemoveProperty(attr.GetName())
    xf = UsdGeom.Xformable(prim)
    xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*m[:3, 3]))
    xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(gf(m).ExtractRotationQuat())


def splat(stage, body):
    found = [p for p in Usd.PrimRange(stage.GetPrimAtPath(body))
             if p.GetAttribute('positions') and len(p.GetAttribute('positions').Get() or []) > 1000]
    assert len(found) == 1, (body, [str(p.GetPath()) for p in found])
    return found[0]


def registration(old_prim, new_prim):
    """Fit a rigid raw->old conversion, then verify every corresponding point.

    Do not use ICP: a different reconstruction or reordered point set must fail.
    Both datasets must contain the exact same indexed Gaussian centers.
    """
    raw = np.asarray(new_prim.GetAttribute('positions').Get(), dtype=float)
    old = np.asarray(old_prim.GetAttribute('positions').Get(), dtype=float)
    assert raw.shape == old.shape, 'Different source Gaussian counts'
    indices = np.linspace(0, len(raw) - 1, min(4096, len(raw)), dtype=int)
    x, y = raw[indices], old[indices]
    xc, yc = x.mean(axis=0), y.mean(axis=0)
    u, _, vt = np.linalg.svd((x-xc).T @ (y-yc))
    r = vt.T @ u.T
    assert np.linalg.det(r) > 0, 'Mirrored source geometry'
    m = np.eye(4); m[:3, :3] = r; m[:3, 3] = yc - r @ xc
    errors = np.linalg.norm(points(m, raw) - old, axis=1)
    assert errors.max() < 1e-5, ('Sources do not share an indexed rigid reconstruction', errors.max())
    return m, {'count': len(raw), 'raw_to_donor_geometry': m.tolist(),
               'maximum_center_error_m': float(errors.max()),
               'rms_center_error_m': float(np.sqrt(np.mean(errors**2)))}


def replace_path(path, mapping):
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if path.HasPrefix(Sdf.Path(old)):
            return path.ReplacePrefix(Sdf.Path(old), Sdf.Path(new))
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT/'config/combine_stage.json')
    parser.add_argument('--rebuild', action='store_true', help='Back up and replace this generated scene only')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    donor_path, asset_path, output = [Path(cfg[k]) for k in ('donor_scene', 'asset', 'output_scene')]
    assert donor_path.parent == output.parent, 'Relative environment/sensor paths require the donor directory'
    assert output not in (donor_path, asset_path)
    if output.exists() and not args.rebuild:
        raise FileExistsError(f'{output} already exists; use --rebuild to back up this generated file')
    before = {str(p): sha256(p) for p in (donor_path, asset_path)}
    donor, asset = Usd.Stage.Open(str(donor_path)), Usd.Stage.Open(str(asset_path))
    old_root, new_root = cfg['donor_root'], cfg['target_root']
    asset_root = str(asset.GetDefaultPrim().GetPath())
    report = {'passed': False, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'config': cfg, 'inputs': before, 'registration': {}, 'sensors': []}
    conversions, old_gs, new_gs = {}, {}, {}
    for old_body, new_body in cfg['parts'].items():
        op, npth = old_root+'/'+old_body, asset_root+'/'+new_body
        a, b = splat(donor, op), splat(asset, npth)
        conversions[old_body], report['registration'][old_body] = registration(a, b)
        old_gs[old_body], new_gs[old_body] = str(a.GetPath()), str(b.GetPath())
    base_world = rigid(matrix(donor, old_gs['track_prim']) @ conversions['track_prim'] @
                       np.linalg.inv(matrix(asset, new_gs['track_prim'])))
    report['base_world_matrix'] = base_world.tolist()
    sensors = [p for p in Usd.PrimRange(donor.GetPrimAtPath(old_root))
               if p.GetTypeName() == 'OmniLidar' or p.IsA(UsdGeom.Camera)]
    lidar_counts = {name: sum(p.GetTypeName() == 'OmniLidar' and p.GetParent().GetName().startswith(name+'_')
                             for p in sensors) for name in cfg['expected_lidars']}
    assert lidar_counts == cfg['expected_lidars'], lidar_counts
    assert sum(p.IsA(UsdGeom.Camera) for p in sensors) == cfg['expected_cameras']
    assert len(sensors) == sum(lidar_counts.values()) + cfg['expected_cameras']

    # Keep paths anchored in the final combine_stage directory while building.
    temporary = output.with_name(output.stem+'.building.usda')
    if temporary.exists():
        raise FileExistsError(f'Inspect previous unfinished build before retrying: {temporary}')
    layer = Sdf.Layer.CreateNew(str(temporary)); layer.TransferContent(donor.GetRootLayer())
    stage = Usd.Stage.Open(layer)
    grid = Path(cfg['grid_asset'])
    assert grid.is_file(), 'Run cache_grid_asset.py first'
    stage.GetPrimAtPath('/FlatGrid').GetReferences().SetReferences([
        Sdf.Reference(os.path.relpath(grid, output.parent).replace(os.sep, '/'))])
    assert stage.GetPrimAtPath('/FlatGrid/Environment/Geometry')
    assert stage.RemovePrim(old_root)
    robot = UsdGeom.Xform.Define(stage, new_root).GetPrim()
    robot.GetPayloads().AddPayload(os.path.relpath(asset_path, output.parent).replace(os.sep, '/'))
    set_pose(robot, base_world)
    mapping = {old_root: new_root}
    for old_body, new_body in cfg['parts'].items():
        mapping[old_root+'/'+old_body] = new_root+'/'+new_body
    for sensor in sensors:
        mount = sensor.GetParent() if sensor.GetTypeName() == 'OmniLidar' else sensor
        body = mount.GetParent(); old_body = body.GetName()
        assert old_body in cfg['parts'], f'Unmapped sensor parent: {body.GetPath()}'
        new_body = cfg['parts'][old_body]
        dest_mount = new_root+'/'+new_body+'/'+mount.GetName()
        assert donor.GetRootLayer().GetPrimAtPath(mount.GetPath()), 'Mount must have a donor scene spec'
        Sdf.CreatePrimInLayer(layer, Sdf.Path(dest_mount).GetParentPath())
        assert Sdf.CopySpec(donor.GetRootLayer(), mount.GetPath(), layer, dest_mount)
        old_body_raw = np.linalg.inv(matrix(donor, body.GetPath())) @ matrix(donor, old_gs[old_body]) @ conversions[old_body]
        new_body_raw = np.linalg.inv(matrix(asset, asset_root+'/'+new_body)) @ matrix(asset, new_gs[old_body])
        old_body_mount = np.linalg.inv(matrix(donor, body.GetPath())) @ matrix(donor, mount.GetPath())
        new_body_mount = rigid(new_body_raw @ np.linalg.inv(old_body_raw) @ old_body_mount)
        set_pose(stage.GetPrimAtPath(dest_mount), new_body_mount)
        mapping[str(mount.GetPath())] = dest_mount
        dest_sensor = replace_path(sensor.GetPath(), mapping)
        q = gf(new_body_mount).ExtractRotationQuat()
        row = {'name': mount.GetName(), 'type': str(sensor.GetTypeName()),
               'donor_sensor': str(sensor.GetPath()), 'sensor': str(dest_sensor),
               'mount': dest_mount, 'parent_frame': new_body,
               'translation_m': new_body_mount[:3, 3].tolist(),
               'quaternion_wxyz': [q.GetReal(), *q.GetImaginary()],
               'parent_from_mount': new_body_mount.tolist(),
               'raw_from_mount': (np.linalg.inv(old_body_raw) @ old_body_mount).tolist()}
        # Compare coordinates of all Gaussian centers as seen from the mount.
        new_points = np.asarray(asset.GetPrimAtPath(new_gs[old_body]).GetAttribute('positions').Get())
        old_points = np.asarray(donor.GetPrimAtPath(old_gs[old_body]).GetAttribute('positions').Get())
        old_mount_geometry = np.linalg.inv(matrix(donor, mount.GetPath())) @ matrix(donor, old_gs[old_body])
        new_mount_geometry = np.linalg.inv(matrix(stage, dest_mount)) @ matrix(stage, new_gs[old_body].replace(asset_root, new_root, 1))
        error = float(np.linalg.norm(points(old_mount_geometry, old_points) - points(new_mount_geometry, new_points), axis=1).max())
        assert error < 2e-5, (mount.GetName(), error)
        row['maximum_attachment_error_m'] = error
        target = stage.GetPrimAtPath(dest_sensor)
        # Every sensor property is retained, including the complete emitter arrays.
        compared = 0
        for a in sensor.GetAttributes():
            if sensor == mount and a.GetName().startswith('xformOp'): continue
            b = target.GetAttribute(a.GetName())
            assert b and a.GetTypeName() == b.GetTypeName() and a.Get() == b.Get(), (str(dest_sensor), a.GetName())
            compared += 1
        row['equal_sensor_attributes'] = compared
        if sensor.GetTypeName() == 'OmniLidar':
            for key in ('omni:sensor:Core:scanType', 'omni:sensor:Core:scanRateBaseHz',
                        'omni:sensor:Core:instantLidar', 'omni:sensor:Core:numberOfEmitters'):
                row[key] = sensor.GetAttribute(key).Get()
            row['mount_to_emitter'] = (np.linalg.inv(matrix(stage, dest_mount)) @ matrix(stage, dest_sensor)).tolist()
        report['sensors'].append(row)

    # Retarget RenderProducts and graph relationships/connections to the new bodies.
    for prim in stage.Traverse():
        for rel in prim.GetRelationships():
            old = rel.GetTargets(); new = [replace_path(p, mapping) for p in old]
            if new != old: rel.SetTargets(new)
        for attr in prim.GetAttributes():
            old = attr.GetConnections(); new = [replace_path(p, mapping) for p in old]
            if new != old: attr.SetConnections(new)
    stage.RemovePrim('/World/Stage10BaseAnchor')
    anchor = UsdPhysics.FixedJoint.Define(stage, '/World/ContractBaseAnchor')
    anchor.CreateBody1Rel().SetTargets([new_root+'/track_link'])
    anchor.CreateLocalPos0Attr(Gf.Vec3f(*base_world[:3, 3])); anchor.CreateLocalPos1Attr(Gf.Vec3f(0))
    anchor.CreateLocalRot0Attr(Gf.Quatf(gf(base_world).ExtractRotationQuat()))
    anchor.CreateLocalRot1Attr(Gf.Quatf(1))
    # Keep inherited environment overview; add a closer robot inspection camera.
    camera = UsdGeom.Camera.Define(stage, '/World/ContractOverview')
    target = base_world[:3, 3] + np.array([2., 0., 2.])
    eye = target + np.array([11., -16., 9.])
    camera.CreateFocalLengthAttr(35); camera.CreateClippingRangeAttr(Gf.Vec2f(.05, 10000))
    camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0,0,1)).GetInverse())
    data = dict(layer.customLayerData)
    for key in ('stage10', 'myairyConversion'): data.pop(key, None)
    data['omni_layer'] = {'authoring_layer': './'+output.name}
    data['cameraSettings'] = {'boundCamera': '/World/ContractOverview',
                              'Perspective': {'position': Gf.Vec3d(*eye), 'target': Gf.Vec3d(*target)}}
    data['sensorVisualizer'] = {'version': 'contract_sensors_v1', 'sourceScene': donor_path.name,
                                'contractAsset': str(asset_path), 'rootPolicy': cfg['root_policy'],
                                'mountPolicy': cfg['mount_policy'], 'jointZeroPolicy': 'Contract bind angles are all zero'}
    layer.customLayerData = data
    for prim in stage.Traverse():
        for prop in prim.GetProperties():
            paths = prop.GetTargets() if isinstance(prop, Usd.Relationship) else prop.GetConnections()
            for p in paths:
                assert not p.HasPrefix(Sdf.Path(old_root)), (prop.GetPath(), p)
                if p.HasPrefix(Sdf.Path(new_root)):
                    assert stage.GetPrimAtPath(p.GetPrimPath()), ('Missing target', p)
    assert len([p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]) == 1
    joints = [p for p in Usd.PrimRange(stage.GetPrimAtPath(new_root)) if p.IsA(UsdPhysics.RevoluteJoint)]
    assert len(joints) == 4
    assert all(UsdPhysics.DriveAPI(p, 'angular').GetTargetPositionAttr().Get() == 0 for p in joints)
    assert not stage.GetPrimAtPath(old_root)
    for p, digest in before.items(): assert sha256(p) == digest
    layer.Save()
    if output.exists():
        backups = ROOT/'reports/combine_stage/backups'; backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, backups/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f_')+output.name))
    os.replace(temporary, output)
    local_copy = ROOT/'scenes'/output.name; local_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, local_copy)
    report.update(passed=True, scene=str(output), scene_sha256=sha256(output), lidar_counts=lidar_counts,
                  camera_count=cfg['expected_cameras'], joint_count=len(joints),
                  validation_scope='All indexed mount geometry, all sensor attributes, graph targets, joint zero angles; runtime validation separate',
                  grid_cache_manifest=json.loads((grid.parent/'source_manifest.json').read_text()),
                  external_dependencies=['OmniPBR.mdl is supplied by the installed Isaac Sim material library'])
    write_json(ROOT/'reports/combine_stage/build.json', report)
    print(json.dumps({k: report[k] for k in ('passed', 'scene', 'scene_sha256', 'lidar_counts', 'camera_count')}, indent=2))


if __name__ == '__main__':
    main()
