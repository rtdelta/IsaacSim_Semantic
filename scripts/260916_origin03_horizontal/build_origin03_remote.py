"""Create origin-rebased USD copies; never save a source layer. Run with USD Python."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

BASE = Path('/root/gpufree-data/IsaacSim_Asset')
FOLDER = BASE / 'excavator_module_set/Sim_Fangshan_02'
SCENES = BASE / 'combine_stage'
SOURCE = FOLDER / 'Excavator_Fangshan_05.usda'
TARGET = FOLDER / 'Excavator_Fangshan_05_origin03.usda'
SCENE_SOURCE = SCENES / 'combine_scene_11.usda'
SCENE_TARGET = SCENES / 'combine_scene_11_origin03.usda'
DATA = FOLDER / 'Excavator_Fangshan_05_origin03_data'
ROOT = '/Excavator'
INSTANCE = '/Excavator_Fangshan_05'
BODIES = ['track_prim', 'cab_prim', 'boom_prim', 'arm_prim', 'bucket_prim']
D = np.array([0.05816097110509872, 0.034142205119133, 0.10500001907348633])
POLICY = ('Origin corresponds to the original 03 track origin; unchanged XYZ directions. '
          'Source track geometry is a pure uniform 2.4 scale in this frame. '
          'Not a surveyed ground or center-of-mass datum.')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translate(stage, path, value):
    prim = stage.GetPrimAtPath(path)
    assert prim, path
    attr = prim.GetAttribute('xformOp:translate')
    if not attr:
        xf = UsdGeom.Xformable(prim)
        assert xf, ('Not xformable', path, prim.GetTypeName())
        attr = xf.AddTranslateOp().GetAttr()
    attr.Set(Gf.Vec3d(*map(float, value)))


def offset(stage, path, delta):
    prim = stage.GetPrimAtPath(path)
    xf = UsdGeom.Xformable(prim)
    assert xf, ('Not xformable', path, prim.GetTypeName())
    # Existing transforms are TRS, with translate outermost in parent coordinates.
    mat = xf.GetLocalTransformation()
    if not xf.GetOrderedXformOps():
        translate(stage, path, delta)
    elif prim.GetAttribute('xformOp:translate'):
        old = prim.GetAttribute('xformOp:translate').Get()
        translate(stage, path, np.array(old) + delta)
    else:
        # Preserve referenced transforms by appending a parent-space offset.
        shifted = mat * Gf.Matrix4d(1).SetTranslate(Gf.Vec3d(*map(float, delta)))
        xf.MakeMatrixXform().Set(shifted)


def clone(source, target, scene=False):
    assert not target.exists(), f'Refusing to overwrite {target}'
    layer = Sdf.Layer.CreateNew(str(target))
    layer.TransferContent(Sdf.Layer.FindOrOpen(str(source)))
    layer.Save()
    return masked(target, INSTANCE) if scene else Usd.Stage.Open(str(target), load=Usd.Stage.LoadNone)


def masked(path, root, sensors=()):
    mask = Usd.StagePopulationMask()
    for body in BODIES:
        for group in ('GS', 'Mesh', 'URDFReference'):
            mask.Add(root + '/' + body + '/Visuals/' + group + '/__probe__')
    mask.Add(root + '/Joints')
    mask.Add(root + '/URDFOverlay/__probe__')
    for sensor in sensors:
        mask.Add(sensor + '/__probe__')
    mask.Add('/World/Stage10BaseAnchor')
    return Usd.Stage.OpenMasked(str(path), mask)


def matrix(stage, path):
    prim = stage.GetPrimAtPath(path)
    assert prim, path
    return np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T


def main():
    assert sha(SOURCE) == '2588447b27194306f20b25c28a54b470e22162c158db29345c55b06256ab3280'
    assert sha(SCENE_SOURCE) == '5f0d7a91568a7e44c796d1e62b75ea0c5ca838f890c45a115aa8d0ab1f29c437'
    assert not TARGET.exists() and not SCENE_TARGET.exists() and not DATA.exists()
    originals = [FOLDER / f'Excavator_Fangshan_{n}.usda' for n in ('03', '04', '05')]
    originals += [SCENES / f'combine_scene_{n}.usda' for n in ('08', '10', '11')]
    originals += list((FOLDER / 'Excavator_Fangshan_05_data').rglob('*'))
    before = {str(p): sha(p) for p in originals if p.is_file()}
    DATA.mkdir()

    stage = clone(SOURCE, TARGET)
    root = stage.GetPrimAtPath(ROOT)
    root.SetDisplayName('Excavator Fangshan 05 - original 03 track origin')
    root.SetCustomDataByKey('version', '05_origin03')
    root.SetCustomDataByKey('baseOriginPolicy', POLICY)
    root.SetCustomDataByKey('originRevision', 'origin03_v1')
    root.SetCustomDataByKey('originShiftFrom05', Gf.Vec3d(*D))
    root.SetCustomDataByKey('overlayPolicy', 'URDF and pin overlay retains its previous geometric placement; URDF base is at -originShiftFrom05 in the revised base frame.')
    for group in ('GS', 'Mesh'):
        offset(stage, ROOT + '/track_prim/Visuals/' + group, -D)
    offset(stage, ROOT + '/track_prim/Visuals/URDFReference', -D)
    offset(stage, ROOT + '/URDFOverlay', -D)
    for body in BODIES[1:]:
        offset(stage, ROOT + '/' + body, -D)
    com = stage.GetPrimAtPath(ROOT + '/track_prim').GetAttribute('physics:centerOfMass')
    com.Set(Gf.Vec3f(*map(float, np.array(com.Get()) - D)))
    j = UsdPhysics.Joint(stage.GetPrimAtPath(ROOT + '/Joints/swing'))
    j.GetLocalPos0Attr().Set(Gf.Vec3f(*map(float, np.array(j.GetLocalPos0Attr().Get()) - D)))
    stage.GetRootLayer().Save()

    scene = clone(SCENE_SOURCE, SCENE_TARGET, scene=True)
    robot = scene.GetPrimAtPath(INSTANCE)
    robot.GetPayloads().ClearPayloads()
    robot.GetPayloads().AddPayload('../excavator_module_set/Sim_Fangshan_02/' + TARGET.name)
    robot.SetDisplayName('Excavator 05 origin03 | scene 11 copy')
    robot.SetCustomDataByKey('originRevision', 'origin03_v1')
    robot.SetCustomDataByKey('stage10:groundDatum', 'World geometry and ground clearance preserved from scene 11; root coordinate changed to original 03 track origin.')
    old_root = UsdGeom.Xformable(robot).GetLocalTransformation()
    old_root.SetTranslateOnly(old_root.Transform(Gf.Vec3d(*D)))
    translate(scene, INSTANCE, old_root.ExtractTranslation())
    for body in BODIES[1:]:
        offset(scene, INSTANCE + '/' + body, -D)
    anchor = UsdPhysics.Joint(scene.GetPrimAtPath('/World/Stage10BaseAnchor'))
    anchor.GetLocalPos1Attr().Set(Gf.Vec3f(*map(float, np.array(anchor.GetLocalPos1Attr().Get()) - D)))
    scene.GetRootLayer().Save()

    # Sensor mount specs belong to the scene and are never rewritten.
    mounts = [str(p.path) for p in scene.GetRootLayer().GetPrimAtPath(INSTANCE + '/cab_prim').nameChildren
              if p.name.startswith('My')]
    mounts.append(INSTANCE + '/boom_prim/Camera')
    assert len(mounts) == 14, mounts
    old, new = masked(SCENE_SOURCE, INSTANCE, mounts), masked(SCENE_TARGET, INSTANCE, mounts)
    errors, mount_errors = {}, {}
    for body in BODIES:
        for group in ('GS', 'Mesh', 'URDFReference'):
            path = INSTANCE + '/' + body + '/Visuals/' + group
            errors[path] = float(np.max(np.abs(matrix(old, path) - matrix(new, path))))
    errors['overlay'] = float(np.max(np.abs(matrix(old, INSTANCE + '/URDFOverlay') - matrix(new, INSTANCE + '/URDFOverlay'))))
    for path in mounts:
        mount_errors[path] = float(np.max(np.abs(matrix(old, path) - matrix(new, path))))
        a, b = old.GetPrimAtPath(path), new.GetPrimAtPath(path)
        for attr in ('xformOp:translate', 'xformOp:orient', 'xformOp:scale', 'xformOpOrder'):
            assert a.GetAttribute(attr).Get() == b.GetAttribute(attr).Get(), (path, attr)
    assert max(errors.values()) < 1e-9, errors
    assert max(mount_errors.values()) < 1e-9, mount_errors
    joint_errors = {}
    for prim in new.Traverse():
        if not prim.IsA(UsdPhysics.Joint):
            continue
        joint = UsdPhysics.Joint(prim)
        points = []
        for rel, attr in ((joint.GetBody0Rel(), joint.GetLocalPos0Attr()), (joint.GetBody1Rel(), joint.GetLocalPos1Attr())):
            body = rel.GetTargets()
            m = matrix(new, str(body[0])) if body else np.eye(4)
            points.append((m @ np.array([*attr.Get(), 1.]))[:3])
        joint_errors[str(prim.GetPath())] = float(np.linalg.norm(points[0] - points[1]))
    assert max(joint_errors.values()) < 2e-6, joint_errors
    k = json.loads((FOLDER / 'Excavator_Fangshan_05_data/kinematics_05.json').read_text())
    k['version'] = '05_origin03'
    k['base_origin_policy'] = POLICY
    k['origin_shift_from_05_m'] = D.tolist()
    for i, joint in enumerate(k['joints']):
        joint['zero_pivot_in_base_m'] = (np.array(joint['zero_pivot_in_base_m']) - D).tolist()
        if i == 0:
            joint['origin_xyz_m'] = (np.array(joint['origin_xyz_m']) - D).tolist()
            m = np.array(joint['T_parent_from_joint']); m[:3, 3] -= D
            joint['T_parent_from_joint'] = m.tolist()
    (DATA / 'kinematics_origin03.json').write_text(json.dumps(k, indent=2))
    assert before == {p: sha(Path(p)) for p in before}, 'Source modified'
    report = {'passed': True, 'asset': str(TARGET), 'scene': str(SCENE_TARGET),
        'origin_shift_from_05_m': D.tolist(), 'policy': POLICY,
        'new_root_world_m': matrix(new, INSTANCE)[:3, 3].tolist(),
        'geometry_world_matrix_errors': errors, 'sensor_world_matrix_errors': mount_errors,
        'joint_anchor_errors_m': joint_errors, 'sensor_mounts_unchanged': True,
        'original_sha256': before, 'asset_sha256': sha(TARGET), 'scene_sha256': sha(SCENE_TARGET)}
    (DATA / 'validation.json').write_text(json.dumps(report, indent=2))
    (DATA / 'README.md').write_text('# Origin 03 revision\n\n' + POLICY + '\n\n'
        'Payload asset: ' + str(TARGET) + '\n\nScene copy: ' + str(SCENE_TARGET) + '\n\n'
        'Geometry scale stays 2.4. Joint rotations, axes, signs, drives, sensor mount transforms and prim paths are preserved. '
        'Only coordinates are rebased; the copied scene compensates the instance transform and world anchor. '
        'URDF overlay keeps its previous placement, so its base datum is offset from the new track datum. '
        'All original files are unchanged; validation.json includes their SHA-256 hashes.\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
