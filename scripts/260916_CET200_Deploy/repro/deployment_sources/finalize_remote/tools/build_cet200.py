"""Run inside Isaac Sim Kit. Convert the preserved upstream URDF into USD."""
import asyncio
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import traceback
import xml.etree.ElementTree as ET

import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdUtils, PhysxSchema

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
MAIN_JOINTS = ('Hinge_Slew', 'Hinge_Boom', 'Hinge_Arm', 'Hinge_Bucket')


def progress(phase):
    (REPORTS / 'build_progress.json').write_text(json.dumps({'phase': phase}))
    print('CET200_BUILD', phase, flush=True)


def settings(stage):
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)


async def main():
    app = omni.kit.app.get_app()
    report = {'passed': False, 'isaac_version': Path('/root/isaacsim/VERSION').read_text().strip()}
    try:
        progress('enable_importer')
        assert app.get_extension_manager().set_extension_enabled_immediate('isaacsim.asset.importer.urdf', True)
        await app.next_update_async()
        from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
        source = ROOT / 'source'
        urdf_path = source / 'cet200_description/urdf/cet200.urdf'
        xml = ET.parse(urdf_path).getroot()
        joint_data = []
        for joint in xml.findall('joint'):
            row = {'name': joint.get('name'), 'type': joint.get('type')}
            for tag in ('parent', 'child', 'origin', 'axis', 'limit'):
                el = joint.find(tag)
                row[tag] = dict(el.attrib) if el is not None else None
            joint_data.append(row)
        report['source'] = {
            'url': 'https://github.com/vmc-motion/cet200',
            'commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
            'license': 'Apache-2.0',
            'urdf_sha256': hashlib.sha256(urdf_path.read_bytes()).hexdigest(),
            'links': len(xml.findall('link')), 'joints': len(joint_data),
            'collision_elements': len(xml.findall('link/collision')),
        }
        (REPORTS / 'source_joints.json').write_text(json.dumps(joint_data, indent=2))
        config = URDFImporterConfig(
            urdf_path=str(ROOT / 'prepared/cet200_description/urdf/cet200.urdf'), usd_path=str(ROOT / 'usd/imported_normalized'),
            ros_package_paths=[{'name': 'cet200_description', 'path': str(ROOT / 'prepared/cet200_description')}],
            merge_fixed_joints=True, merge_mesh=False, fix_base=True,
            collision_from_visuals=False, allow_self_collision=False,
            run_asset_transformer=True, run_multi_physics_conversion=True,
        )
        report['import_config'] = dataclasses.asdict(config)
        progress('convert_urdf')
        imported_path = Path(URDFImporter(config).import_urdf())
        report['imported_asset'] = str(imported_path.relative_to(ROOT))
        progress('author_payload_asset')
        asset_path = ROOT / 'usd/CET200.usda'
        assert not asset_path.exists()
        asset = Usd.Stage.CreateNew(str(asset_path))
        settings(asset)
        robot = UsdGeom.Xform.Define(asset, '/CET200').GetPrim()
        asset.SetDefaultPrim(robot)
        robot.SetMetadata('kind', 'component')
        robot.GetReferences().AddReference(os.path.relpath(imported_path, asset_path.parent))
        robot.SetCustomDataByKey('deployment:sourceCommit', report['source']['commit'])
        robot.SetCustomDataByKey('deployment:sourceUrl', report['source']['url'])
        robot.SetCustomDataByKey('deployment:geometryScale', 1.0)
        robot.SetCustomDataByKey('deployment:note', 'Fixed-base URDF import; provisional drives, not a hydraulic simulation.')
        joints = [p for p in asset.Traverse() if p.IsA(UsdPhysics.RevoluteJoint)]
        report['revolute_joints'] = [str(p.GetPath()) for p in joints]
        report['main_joints'] = {}
        for name in MAIN_JOINTS:
            found = [p for p in joints if p.GetName() == name]
            assert len(found) == 1, (name, [p.GetName() for p in joints])
            prim = found[0]
            joint = UsdPhysics.RevoluteJoint(prim)
            drive = UsdPhysics.DriveAPI.Apply(prim, 'angular')
            drive.CreateTypeAttr('acceleration')
            drive.CreateTargetPositionAttr(0.0)
            drive.CreateTargetVelocityAttr(0.0)
            drive.CreateStiffnessAttr(1000.0)
            drive.CreateDampingAttr(100.0)
            drive.CreateMaxForceAttr(float('inf'))
            report['main_joints'][name] = {
                'path': str(prim.GetPath()), 'axis': joint.GetAxisAttr().Get(),
                'lower_deg': joint.GetLowerLimitAttr().Get(), 'upper_deg': joint.GetUpperLimitAttr().Get(),
                'body0': [str(x) for x in joint.GetBody0Rel().GetTargets()],
                'body1': [str(x) for x in joint.GetBody1Rel().GetTargets()],
            }
        for prim in asset.Traverse():
            if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                api = PhysxSchema.PhysxArticulationAPI.Apply(prim)
                api.CreateEnabledSelfCollisionsAttr(False)
                api.CreateSolverPositionIterationCountAttr(16)
                api.CreateSolverVelocityIterationCountAttr(4)
        asset.GetRootLayer().Save()
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'], useExtentsHint=False)
        bounds = cache.ComputeWorldBound(robot).ComputeAlignedRange()
        lo, hi = bounds.GetMin(), bounds.GetMax()
        report['bounds_m'] = {'min': list(lo), 'max': list(hi), 'size': list(hi - lo)}
        report['geometry_scale'] = [1, 1, 1]
        report['mesh_count'] = sum(p.IsA(UsdGeom.Mesh) for p in Usd.PrimRange.Stage(asset, Usd.TraverseInstanceProxies()))
        report['rigid_body_count'] = sum(p.HasAPI(UsdPhysics.RigidBodyAPI) for p in asset.Traverse())
        assert report['mesh_count'] > 0 and all(math.isfinite(x) for x in list(lo) + list(hi))
        assert 4 < float(hi[0] - lo[0]) < 20, report['bounds_m']
        assert 2 < float(hi[1] - lo[1]) < 4, report['bounds_m']
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(asset_path))
        report['dependencies'] = {'layers': [l.identifier for l in layers], 'assets': list(assets), 'unresolved': list(unresolved)}
        assert not unresolved, unresolved
        progress('author_preview')
        preview_path = ROOT / 'usd/CET200_preview.usda'
        preview = Usd.Stage.CreateNew(str(preview_path))
        settings(preview)
        world = UsdGeom.Xform.Define(preview, '/World').GetPrim()
        preview.SetDefaultPrim(world)
        payload = UsdGeom.Xform.Define(preview, '/World/CET200').GetPrim()
        payload.GetPayloads().AddPayload('./CET200.usda')
        scene = UsdPhysics.Scene.Define(preview, '/World/PhysicsScene')
        scene.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
        scene.CreateGravityMagnitudeAttr(0.0)
        scene.GetPrim().SetCustomDataByKey('deployment:note', 'Zero gravity for joint inspection, not a calibrated dynamic scene.')
        ground = UsdGeom.Cube.Define(preview, '/World/Ground')
        ground.CreateSizeAttr(1)
        ground.AddTranslateOp().Set(Gf.Vec3d(0, 0, float(lo[2]) - .11))
        ground.AddScaleOp().Set(Gf.Vec3f(30, 30, .2))
        ground.CreateDisplayColorAttr([Gf.Vec3f(.18, .20, .23)])
        UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
        light = UsdLux.DomeLight.Define(preview, '/World/DomeLight')
        light.CreateIntensityAttr(800)
        sun = UsdLux.DistantLight.Define(preview, '/World/Sun')
        sun.CreateIntensityAttr(2000)
        sun.AddRotateXYZOp().Set(Gf.Vec3f(-35, -25, -30))
        camera = UsdGeom.Camera.Define(preview, '/World/Camera')
        center = (lo + hi) * .5
        eye = center + Gf.Vec3d(11, -16, 10)
        camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, center, Gf.Vec3d(0, 0, 1)).GetInverse())
        camera.CreateClippingRangeAttr(Gf.Vec2f(.1, 1000))
        camera.CreateFocalLengthAttr(35)
        preview.GetRootLayer().customLayerData = {'cameraSettings': {'Perspective': {'position': eye, 'target': center}, 'boundCamera': '/World/Camera'}}
        preview.GetRootLayer().Save()
        check = Usd.Stage.Open(str(preview_path))
        assert check.GetPrimAtPath('/World/CET200').IsLoaded()
        assert len([p for p in check.Traverse() if p.IsA(UsdPhysics.RevoluteJoint)]) == len(joints)
        report['payload_composition_passed'] = True
        report['asset_path'] = str(asset_path)
        report['preview_path'] = str(preview_path)
        report['passed'] = True
        progress('passed')
    except Exception:
        report['error'] = traceback.format_exc()
        print(report['error'], flush=True)
        progress('failed')
    (REPORTS / 'build_report.json').write_text(json.dumps(report, indent=2))
    app.post_quit(0 if report['passed'] else 1)


asyncio.ensure_future(main())
