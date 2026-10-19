"""Restore scene16 backgrounds, with backup and USD/texture validation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from usd_environment import initialize
initialize()
from pxr import Ar, Sdf, Usd, UsdGeom
from background_options import BACKGROUND_NODES, restore_background_options

ROOT = Path(__file__).resolve().parents[1]
SCENE = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    if digest(SCENE) != args.expected_sha256:
        raise RuntimeError('Scene changed since inspection; inspect before updating')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    out = ROOT/'reports/background_options'/stamp
    out.mkdir(parents=True, exist_ok=False)
    backup = out/('before_'+SCENE.name)
    shutil.copy2(SCENE, backup)
    stage = Usd.Stage.Open(str(SCENE), load=Usd.Stage.LoadNone)
    before_metadata = dict(stage.GetRootLayer().customLayerData)
    before_layers = list(stage.GetRootLayer().subLayerPaths)
    old_files = [SCENE.parent/'combine_scene_15_surround_fisheye.usda',
                 SCENE.parent/'combine_scene_13_3dgs_contract.usda']
    old_hashes = {str(p): digest(p) for p in old_files}
    restore_background_options(stage)
    stage.Load('/environment_Fangshan_02')
    stage.Load('/World/Excavator')
    errors = [str(e) for e in stage.GetCompositionErrors()]
    if errors:
        raise RuntimeError(json.dumps(errors))
    nodes = []
    for name, path in BACKGROUND_NODES.items():
        p = stage.GetPrimAtPath(path)
        assert p and p.IsActive(), path
        visible = p.GetAttribute('visibility').Get()
        assert visible != 'invisible', path
        nodes.append(dict(name=name, path=path, type=p.GetTypeName(), active=p.IsActive(), visibility=visible))
    gs = stage.GetPrimAtPath(BACKGROUND_NODES['original_3dgs_ground'])
    assert gs.GetTypeName() == 'ParticleField3DGaussianSplat'
    centers = gs.GetAttribute('positions').Get()
    assert centers is not None and len(centers) > 0
    textures = {}
    for prefix in ('/FlatGrid', '/environment_Fangshan_02'):
        for p in Usd.PrimRange(stage.GetPrimAtPath(prefix)):
            for attr in p.GetAttributes():
                if attr.GetTypeName() != Sdf.ValueTypeNames.Asset:
                    continue
                v = attr.Get()
                if not v or not v.path or Path(v.path).suffix.lower() not in ('.png','.jpg','.jpeg','.exr','.hdr','.tif','.tiff'):
                    continue
                assert v.resolvedPath, 'Unresolved texture: '+str(attr.GetPath())
                asset = Ar.GetResolver().OpenAsset(Ar.ResolvedPath(v.resolvedPath))
                assert asset and asset.GetSize() > 0, v.resolvedPath
                textures[v.resolvedPath] = dict(bytes=asset.GetSize(), example_attribute=str(attr.GetPath()))
    lidar_count = sum(p.GetTypeName() == 'OmniLidar' for p in stage.Traverse())
    camera_count = sum(p.IsA(UsdGeom.Camera) for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Excavator')))
    assert lidar_count == 13 and camera_count == 5, (lidar_count, camera_count)
    assert list(stage.GetRootLayer().subLayerPaths) == before_layers
    for key, value in before_metadata.items():
        if key != 'sensorVisualizerTerrain':
            assert stage.GetRootLayer().customLayerData[key] == value, key
    for path, sha in old_hashes.items():
        assert digest(Path(path)) == sha
    assert digest(SCENE) == args.expected_sha256, 'Concurrent edit before save'
    stage.GetRootLayer().Save()
    report = dict(passed=True, scene=str(SCENE), before_sha256=args.expected_sha256,
                  scene_sha256=digest(SCENE), backup=str(backup), nodes=nodes,
                  gaussian_centers=len(centers), textures=textures, texture_count=len(textures),
                  lidar_count=lidar_count, robot_camera_count=camera_count,
                  collision_enabled=stage.GetPrimAtPath(BACKGROUND_NODES['original_collision_plane']).GetAttribute('physics:collisionEnabled').Get(),
                  preserved_sources=old_hashes, composition_errors=errors,
                  validation='USD composition, original texture readability and sensor presence; no Kit render launched')
    (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    shutil.copy2(SCENE, out/SCENE.name)
    # Return the small USD layer and report for an exact local delivery copy.
    print(json.dumps(dict(report=report, scene_text=SCENE.read_text(), before_scene_text=backup.read_text())))


if __name__ == '__main__':
    main()
