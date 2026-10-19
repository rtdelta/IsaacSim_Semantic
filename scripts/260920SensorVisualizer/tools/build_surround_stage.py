"""Reference the existing fisheye Camera four times; never edit source assets."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from usd_environment import initialize
initialize()
from pxr import Gf, Sdf, Usd, UsdGeom

ASSETS=Path('/root/gpufree-data/IsaacSim_Asset')
CAMERA=ASSETS/'sensor_set/camera_set/fish_eye_camera/fish_eye_camera.usda'
SOURCE=ASSETS/'combine_stage/combine_scene_13_3dgs_contract.usda'
TARGET=ASSETS/'combine_stage/combine_scene_15_surround_fisheye.usda'
MOUNTS=[('front','Front','front',0),('back','Back','back',180),
        ('left','Left','left',90),('right','Right','right',-90)]


def build(output=TARGET):
    output=Path(output).resolve()
    if output.exists():
        raise FileExistsError('Refusing to overwrite existing stage: '+str(output))
    source=Usd.Stage.Open(str(SOURCE))
    camera_source=Usd.Stage.Open(str(CAMERA))
    camera_prim=camera_source.GetPrimAtPath('/World/FisheyeCamera')
    if not camera_prim or not camera_prim.IsA(UsdGeom.Camera):
        raise ValueError('Expected /World/FisheyeCamera in the source asset')
    stage=Usd.Stage.CreateNew(str(output))
    src=source.GetRootLayer()
    for key in ('metersPerUnit','upAxis','timeCodesPerSecond','framesPerSecond',
                'startTimeCode','endTimeCode','defaultPrim','renderSettingsPrimPath','customLayerData'):
        if src.pseudoRoot.HasInfo(key):
            value=src.pseudoRoot.GetInfo(key)
            if key=='customLayerData':
                value['omni_layer']={'authoring_layer':'./'+output.name}
            stage.GetRootLayer().pseudoRoot.SetInfo(key,value)
    stage.GetRootLayer().subLayerPaths=[os.path.relpath(SOURCE,output.parent)]
    parent='/World/Excavator/swing_link'
    cache=UsdGeom.XformCache()
    parent_world=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(parent))
    rows=[]
    for cid,label,lidar,yaw in MOUNTS:
        sensor_path=parent+'/MyAiry_'+lidar+'/sensor'
        sensor=stage.GetPrimAtPath(sensor_path)
        if not sensor or sensor.GetTypeName()!='OmniLidar':
            raise ValueError('Missing position reference '+sensor_path)
        local=(cache.GetLocalToWorldTransform(sensor)*parent_world.GetInverse()).ExtractTranslation()
        camera=stage.DefinePrim(parent+'/Fisheye'+label,'Camera')
        camera.GetReferences().AddReference(os.path.relpath(CAMERA,output.parent),'/World/FisheyeCamera')
        camera.AddAppliedSchema('OmniSensorAPI')
        camera.CreateAttribute('omni:sensor:tickRate',Sdf.ValueTypeNames.Float,custom=False).Set(0.)
        pitch=math.radians(10);y=math.radians(yaw)
        forward=Gf.Vec3d(math.cos(pitch)*math.cos(y),math.cos(pitch)*math.sin(y),-math.sin(pitch))
        right=Gf.Vec3d(math.sin(y),-math.cos(y),0.)
        up=Gf.Cross(right,forward)
        transform=Gf.Matrix4d(1.)
        for i,axis in enumerate((right,up,-forward)):
            transform.SetRow(i,Gf.Vec4d(*axis,0.))
        transform.SetTranslateOnly(local)
        UsdGeom.Xformable(camera).MakeMatrixXform().Set(transform)
        # The old calibration extrinsic describes a different physical mounting.
        camera.GetAttribute('aif:lidarToCamera').Block()
        camera.SetCustomDataByKey('sensorVisualizer',{
            'cameraId':cid,'positionSource':sensor_path,'placementPolicy':'copy sensor origin once; independent thereafter',
            'cameraAsset':str(CAMERA),'cameraAssetPrim':'/World/FisheyeCamera',
            'sourceSha256':hashlib.sha256(CAMERA.read_bytes()).hexdigest(),
            'sourceExtrinsicApplied':False,'yawInParentDeg':float(yaw),'downwardPitchDeg':10.})
        camera_world=transform*parent_world
        delta=(camera_world.ExtractTranslation()-cache.GetLocalToWorldTransform(sensor).ExtractTranslation()).GetLength()
        if delta>1e-8 or abs(transform.GetDeterminant()-1)>1e-8:
            raise AssertionError('Non-rigid or misaligned camera '+cid)
        rows.append({'id':cid,'prim':str(camera.GetPath()),'sensor':sensor_path,
                     'position_in_parent':list(local),'origin_error_m':delta,
                     'forward_in_parent':list(forward),'resolution':list(camera.GetAttribute('omni:lensdistortion:opencvFisheye:imageSize').Get())})
    errors=[str(e) for e in stage.GetCompositionErrors()]
    if errors: raise RuntimeError(json.dumps(errors))
    stage.GetRootLayer().Save()
    report={'scene':str(output),'source_camera':str(CAMERA),'cameras':rows,
            'lidars':sum(p.GetTypeName()=='OmniLidar' for p in stage.Traverse()),
            'meters_per_unit':UsdGeom.GetStageMetersPerUnit(stage)}
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(TARGET));args=parser.parse_args()
    build(args.output)
