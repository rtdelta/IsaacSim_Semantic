"""Create scene16 as a stronger layer; never edit scene15 or source assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from usd_environment import initialize
initialize()
from pxr import Gf, Sdf, Usd, UsdGeom
from background_options import restore_background_options

ASSETS=Path('/root/gpufree-data/IsaacSim_Asset')
ROOT=Path(__file__).resolve().parents[1]


def build(terrain, output):
    terrain=Path(terrain).resolve();output=Path(output).resolve()
    source=ASSETS/'combine_stage/combine_scene_15_surround_fisheye.usda'
    if output.exists():raise FileExistsError('Refusing to replace '+str(output))
    cfg=json.loads((terrain.parent/'terrain_config.json').read_text())
    probe=Usd.Stage.Open(str(terrain),load=Usd.Stage.LoadNone)
    if not probe.GetPrimAtPath('/Terrain'):raise ValueError('Missing /Terrain export root')
    source_layer=Sdf.Layer.FindOrOpen(str(source))
    stage=Usd.Stage.CreateNew(str(output))
    layer=stage.GetRootLayer();layer.subLayerPaths=[os.path.relpath(source,output.parent)]
    # Kit reads renderer configuration from the root layer; a sublayer alone
    # does not inherit those application settings when a new scene is opened.
    for key in ('metersPerUnit','upAxis','timeCodesPerSecond','framesPerSecond',
                'startTimeCode','endTimeCode','defaultPrim','renderSettingsPrimPath','customLayerData'):
        if source_layer.pseudoRoot.HasInfo(key):
            layer.pseudoRoot.SetInfo(key,source_layer.pseudoRoot.GetInfo(key))
    stage.Load('/World/Excavator',Usd.LoadWithoutDescendants)
    UsdGeom.SetStageMetersPerUnit(stage,1.)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    stage.SetDefaultPrim(stage.GetPrimAtPath('/World'))
    stage.SetTimeCodesPerSecond(60)
    root=stage.DefinePrim('/World/UndulatingGround','Xform')
    root.GetReferences().AddReference(os.path.relpath(terrain,output.parent),'/Terrain')
    UsdGeom.Xformable(root).AddTranslateOp().Set(Gf.Vec3d(*cfg['center_world_m']))
    root.SetCustomDataByKey('terrainConfigJson',json.dumps(cfg,sort_keys=True))
    info={'sourceScene':str(source),'terrainAsset':str(terrain),
          'terrainSha256':hashlib.sha256(terrain.read_bytes()).hexdigest(),
          'configJson':json.dumps(cfg,sort_keys=True),'groundFollowing':False,
          'oldGroundHiddenJson':'[]'}
    metadata=dict(layer.customLayerData)
    metadata.update(sensorVisualizerTerrain=info,omni_layer={'authoring_layer':'./'+output.name})
    layer.customLayerData=metadata
    backgrounds=restore_background_options(stage)
    info=dict(layer.customLayerData['sensorVisualizerTerrain'])
    errors=[str(e) for e in stage.GetCompositionErrors()]
    if errors:raise RuntimeError(json.dumps(errors))
    layer.Save()
    mesh_data=[]
    for prim in Usd.PrimRange(root):
        if prim.IsA(UsdGeom.Mesh):
            mesh=UsdGeom.Mesh(prim);points=mesh.GetPointsAttr().Get()
            valid,reason=UsdGeom.Mesh.ValidateTopology(mesh.GetFaceVertexIndicesAttr().Get(),
                mesh.GetFaceVertexCountsAttr().Get(),len(points))
            if not valid:raise AssertionError(reason)
            mesh_data.append({'prim':str(prim.GetPath()),'vertices':len(points),
                              'bounds_z':[min(p[2] for p in points),max(p[2] for p in points)]})
    if not mesh_data:raise ValueError('No terrain mesh composed')
    report={'scene':str(output),'scene_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'terrain':info,'meshes':mesh_data,'old_ground_hidden':[], 'background_nodes':backgrounds,
            'source_scene_unchanged_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    folder=ROOT/'reports/tilt_terrain';folder.mkdir(parents=True,exist_ok=True)
    (folder/'assembly.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--terrain',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();build(a.terrain,a.output)
