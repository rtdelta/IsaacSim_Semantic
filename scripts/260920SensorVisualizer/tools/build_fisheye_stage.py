"""Create a new, non-destructive scene layer. Run through tools/run_cpu.sh."""
import argparse
import json
import math
from pathlib import Path
from usd_environment import initialize
initialize()
from pxr import Gf, Sdf, Usd, UsdGeom


def build(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError('Refusing to overwrite an existing stage: '+str(destination))
    stage = Usd.Stage.CreateNew(str(destination))
    # Stage-level metrics are read from the root layer, not inherited from sublayers.
    source_layer = Sdf.Layer.FindOrOpen(str(source))
    for key in ('metersPerUnit','upAxis','timeCodesPerSecond','framesPerSecond',
                'startTimeCode','endTimeCode','defaultPrim','renderSettingsPrimPath','customLayerData'):
        if source_layer.pseudoRoot.HasInfo(key):
            value = source_layer.pseudoRoot.GetInfo(key)
            if key == 'customLayerData' and 'omni_layer' in value:
                value['omni_layer']['authoring_layer'] = './'+destination.name
            stage.GetRootLayer().pseudoRoot.SetInfo(key,value)
    import os
    stage.GetRootLayer().subLayerPaths = [os.path.relpath(source, destination.parent)]
    camera = UsdGeom.Camera.Define(stage, '/World/Excavator/swing_link/FisheyeFront')
    prim = camera.GetPrim()
    prim.SetMetadata('apiSchemas', Sdf.TokenListOp.Create(prependedItems=[
        'OmniSensorAPI', 'OmniLensDistortionOpenCvFisheyeAPI']))
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1000.0))
    camera.CreateFocalLengthAttr(10.0)
    camera.CreateHorizontalApertureAttr(20.0)
    camera.CreateVerticalApertureAttr(20.0)
    camera.CreateFocusDistanceAttr(0.)
    camera.CreateFStopAttr(0.)
    # USD camera: -Z forward / +Y up. Here looks along parent +X, 10 deg down.
    a = math.radians(10)
    rotation = Gf.Matrix4d(0,-1,0,0, math.sin(a),0,math.cos(a),0,
                           -math.cos(a),0,math.sin(a),0, 0,0,0,1)
    rotation.SetTranslateOnly(Gf.Vec3d(0.6, -0.9, 2.2))
    UsdGeom.Xformable(prim).AddTransformOp().Set(rotation)
    def attr(name, kind, value):
        prim.CreateAttribute(name, kind, custom=False).Set(value)
    attr('omni:sensor:tickRate', Sdf.ValueTypeNames.Float, 0.)
    attr('omni:lensdistortion:model', Sdf.ValueTypeNames.Token, 'opencvFisheye')
    # Ideal equidistant lens: theta=90deg lands on midpoint of the image edge.
    for name, value in dict(cx=512.,cy=512.,fx=1024/math.pi,fy=1024/math.pi,k1=0.,k2=0.,k3=0.,k4=0.).items():
        attr('omni:lensdistortion:opencvFisheye:'+name, Sdf.ValueTypeNames.Float, value)
    attr('omni:lensdistortion:opencvFisheye:imageSize', Sdf.ValueTypeNames.Int2, Gf.Vec2i(1024,1024))
    prim.SetCustomDataByKey('sensorVisualizer', {'model':'ideal_opencv_equidistant',
        'calibration':'synthetic; not a calibrated physical camera', 'horizontalFovDeg':180.0})
    stage.GetRootLayer().Save()
    errors = [str(e) for e in stage.GetCompositionErrors()]
    lidars = [str(p.GetPath()) for p in stage.Traverse() if p.GetTypeName()=='OmniLidar']
    if errors or len(lidars)!=13 or UsdGeom.GetStageMetersPerUnit(stage)!=1.0:
        raise RuntimeError(json.dumps({'composition_errors':errors,'lidars':len(lidars)}))
    print(json.dumps({'scene':str(destination),'camera':str(prim.GetPath()),'lidars':len(lidars)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source', default='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_13_3dgs_contract.usda')
    parser.add_argument('--output', default='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_14_fisheye.usda')
    args=parser.parse_args()
    build(args.source,args.output)
