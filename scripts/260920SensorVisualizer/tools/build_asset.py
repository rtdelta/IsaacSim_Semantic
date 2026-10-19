"""Build the colleague-contract asset from untouched raw PLYs, without Kit."""
import argparse
import json
from pathlib import Path
import shutil
import numpy as np

from usd_environment import initialize
ISAAC, USD_LIBS, CONVERTER = initialize()
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics
import usd_convert_gsplat
from contract_math import ROOT, load_config, raw_to_base, forward, sha256, write_json


def gf_matrix(column_matrix):
    return Gf.Matrix4d(*np.asarray(column_matrix).T.ravel().tolist())


def init_stage(path, default_path):
    stage=Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1)
    UsdPhysics.SetStageKilogramsPerUnit(stage,1)
    root=UsdGeom.Xform.Define(stage,default_path)
    stage.SetDefaultPrim(root.GetPrim())
    return stage,root


def set_pose(xform, matrix):
    # Unscaled link frames; PhysX-compatible translate + orient ops.
    xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*matrix[:3,3]))
    xform.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(gf_matrix(matrix).ExtractRotationQuat())


def make_preview(bundle, name, cfg):
    stage,world=init_stage(bundle/(name+'_preview.usda'),'/World')
    base=cfg['preview']['base_world_xyz_m']
    robot=UsdGeom.Xform.Define(stage,'/World/Excavator')
    robot.GetPrim().GetPayloads().AddPayload('./'+name+'.usda')
    robot.AddTranslateOp().Set(Gf.Vec3d(*base))
    physics=UsdPhysics.Scene.Define(stage,'/World/PhysicsScene')
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr(0)
    fixed=UsdPhysics.FixedJoint.Define(stage,'/World/PreviewBaseAnchor')
    fixed.CreateBody1Rel().SetTargets(['/World/Excavator/track_link'])
    fixed.CreateLocalPos0Attr(Gf.Vec3f(*base));fixed.CreateLocalPos1Attr(Gf.Vec3f(0))
    fixed.CreateLocalRot0Attr(Gf.Quatf(1));fixed.CreateLocalRot1Attr(Gf.Quatf(1))
    ground=UsdGeom.Cube.Define(stage,'/World/Ground')
    ground.CreateSizeAttr(1)
    xf=UsdGeom.XformCommonAPI(ground)
    xf.SetTranslate(Gf.Vec3d(1,0,base[2]+cfg['preview']['ground_z_in_base_m']-.05))
    xf.SetScale(Gf.Vec3f(24,20,.1));ground.CreateDisplayColorAttr([Gf.Vec3f(.23,.25,.28)])
    ground.GetPrim().SetCustomDataByKey('scope','Preview only: no ground or world anchor in reusable asset')
    dome=UsdLux.DomeLight.Define(stage,'/World/Sky');dome.CreateIntensityAttr(900)
    light=UsdLux.DistantLight.Define(stage,'/World/Sun');light.CreateIntensityAttr(1800)
    UsdGeom.Xformable(light).AddRotateXYZOp().Set(Gf.Vec3f(25,-40,-25))
    camera=UsdGeom.Camera.Define(stage,'/World/Camera')
    camera.CreateFocalLengthAttr(38);camera.CreateClippingRangeAttr(Gf.Vec2f(.1,1000))
    eye=Gf.Vec3d(13,-17,10);target=Gf.Vec3d(2,0,2.3)
    camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye,target,Gf.Vec3d(0,0,1)).GetInverse())
    stage.GetRootLayer().customLayerData={'cameraSettings':{'Perspective':{'position':eye,'target':target},'boundCamera':'/World/Camera'}}
    stage.GetRootLayer().Save()


def build(output=None, rebuild=False):
    cfg=load_config();name=cfg['asset_name'];bundle=Path(output or ROOT/'assets'/name)
    if (bundle/(name+'.usda')).exists() and not rebuild:
        raise FileExistsError('Generated asset exists. Use --rebuild for this project-owned output.')
    bundle.mkdir(parents=True,exist_ok=True);(bundle/'geometry').mkdir(exist_ok=True)
    report={'passed':False,'version':cfg['version'],'asset':name,'parts':{},'converter':{
        'version':usd_convert_gsplat.__version__,'installed_path':str(CONVERTER),
        'writer_sha256':sha256(CONVERTER/'pip_prebundle/usd_convert_gsplat/usd_writer.py'),
        'reader_sha256':sha256(CONVERTER/'pip_prebundle/usd_convert_gsplat/ply_reader.py'),
        'entry_point':'read_ply + write_gaussian_splat_usd; rotation_degrees=(0,0,0), up_axis=Z'}}
    write_json(ROOT/'reports/build.json',report)
    for part in cfg['parts']:
        path=ROOT/'sources/ply'/part['ply']
        if sha256(path)!=part['sha256']:raise ValueError('PLY fingerprint mismatch: '+str(path))
        data=usd_convert_gsplat.read_ply(str(path))
        assert data.count==part['count']
        for array in [data.positions,data.rotations,data.scales,data.opacities,data.f_dc,data.f_rest]:
            assert np.isfinite(array).all(),part['id']
        assert np.min(np.linalg.norm(data.rotations,axis=1))>0
        target=bundle/'geometry'/(part['id']+'.usdc')
        usd_convert_gsplat.write_gaussian_splat_usd(data,str(target),source_file=part['ply'],prim_name='Splat',up_axis='Z',rotation_degrees=(0,0,0))
        gs=Usd.Stage.Open(str(target));UsdGeom.SetStageMetersPerUnit(gs,1)
        gs.GetDefaultPrim().SetCustomDataByKey('rawPlySha256',part['sha256'])
        gs.GetDefaultPrim().SetCustomDataByKey('coordinatePolicy','Unmodified raw reconstruction coordinates; no centering or axis conversion')
        gs.GetRootLayer().Save()
        report['parts'][part['id']]={'count':data.count,'source_sha256':part['sha256'],'geometry_sha256':sha256(target)}
        print('CONVERTED',part['id'],data.count,flush=True)
        del data,gs
    stage,root=init_stage(bundle/(name+'.usda'),'/Excavator')
    root.GetPrim().SetMetadata('kind','component')
    root.GetPrim().SetCustomData({'version':cfg['version'],'frameName':'base_link',
        'angleConvention':'Contract-relative angles, zero at raw reconstruction bind; API radians, USD drive degrees',
        'scope':cfg['scope'],'physicsPolicy':cfg['physics']['purpose'],
        'loadPolicy':'Self-contained relative geometry payloads; no startup callback required'})
    frames=forward(cfg);common=raw_to_base(cfg);p=cfg['physics'];mapping={}
    parents={j['child_frame']:j['parent_frame'] for j in cfg['joints']}
    for part in cfg['parts']:
        frame=part['frame'];path='/Excavator/'+frame
        body=UsdGeom.Xform.Define(stage,path);set_pose(body,frames[frame])
        prim=body.GetPrim();UsdPhysics.RigidBodyAPI.Apply(prim)
        mass=UsdPhysics.MassAPI.Apply(prim)
        mass.CreateMassAttr(p['placeholder_mass_kg']);mass.CreateDiagonalInertiaAttr(Gf.Vec3f(*p['placeholder_diagonal_inertia']))
        mass.CreateCenterOfMassAttr(Gf.Vec3f(0));mass.CreatePrincipalAxesAttr(Gf.Quatf(1))
        apis=prim.GetAppliedSchemas();prim.SetMetadata('apiSchemas',Sdf.TokenListOp.Create(prependedItems=apis+['PhysxRigidBodyAPI']))
        prim.CreateAttribute('physxRigidBody:disableGravity',Sdf.ValueTypeNames.Bool).Set(True)
        prim.SetCustomData({'frameName':frame,'parentFrame':parents.get(frame,'base_link'),'partId':part['id']})
        if frame=='track_link':UsdPhysics.ArticulationRootAPI.Apply(prim)
        local=np.linalg.inv(frames[frame]) @ common
        visual=UsdGeom.Xform.Define(stage,path+'/Visuals')
        visual.AddTransformOp().Set(gf_matrix(local))
        splat=stage.DefinePrim(path+'/Visuals/Splat')
        splat.GetPayloads().AddPayload('./geometry/'+part['id']+'.usdc')
        mapping[frame]={'body_path':path,'geometry_path':str(splat.GetPath()),'part_id':part['id'],
                        'bind_base_from_link':frames[frame].tolist(),'link_from_raw':local.tolist(),
                        'parent_frame':parents.get(frame,'base_link')}
    for j in cfg['joints']:
        joint=UsdPhysics.RevoluteJoint.Define(stage,'/Excavator/Joints/'+j['name'])
        joint.CreateBody0Rel().SetTargets(['/Excavator/'+j['parent_body']])
        joint.CreateBody1Rel().SetTargets(['/Excavator/'+j['child_frame']])
        joint.CreateLocalPos0Attr(Gf.Vec3f(*j['xyz_m']));joint.CreateLocalPos1Attr(Gf.Vec3f(0))
        joint.CreateLocalRot0Attr(Gf.Quatf(1));joint.CreateLocalRot1Attr(Gf.Quatf(1))
        joint.CreateAxisAttr(j['axis']);joint.CreateJointEnabledAttr(True)
        joint.CreateCollisionEnabledAttr(False)
        drive=UsdPhysics.DriveAPI.Apply(joint.GetPrim(),'angular')
        drive.CreateTypeAttr('force');drive.CreateTargetPositionAttr(0);drive.CreateTargetVelocityAttr(0)
        drive.CreateStiffnessAttr(p['drive_stiffness']);drive.CreateDampingAttr(p['drive_damping']);drive.CreateMaxForceAttr(p['drive_max_force'])
        joint.GetPrim().SetCustomData({'angleZero':'Raw reconstruction bind; no old URDF/bag_2 offsets',
                                       'limitPolicy':'No measured hardware limits; bounded motion belongs to controller'})
    stage.GetRootLayer().Save()
    make_preview(bundle,name,cfg)
    shutil.copy2(ROOT/'config/assembly.json',bundle/'assembly.json')
    manifest={'version':cfg['version'],'matrix_convention':'Column vectors; Gf USD matrices are transposed',
        'default_prim':'/Excavator','base_frame_prim':'/Excavator','articulation_root':'/Excavator/track_link',
        'source_config_sha256':sha256(ROOT/'config/assembly.json'),'total_gaussians':sum(x['count'] for x in cfg['parts']),
        'parts':mapping,'raw_to_base':common.tolist(),'joints':cfg['joints'],
        'physical_layout':'Flat sibling rigid bodies; joint relationships establish connectivity. ROS semantic parentFrame is metadata, not a publisher.',
        'files':{f.relative_to(bundle).as_posix():sha256(f) for f in sorted(bundle.rglob('*')) if f.is_file() and f.name!='manifest.json'}}
    write_json(bundle/'manifest.json',manifest)
    report.update(passed=True,total_gaussians=manifest['total_gaussians'],output=str(bundle))
    write_json(ROOT/'reports/build.json',report)
    print('BUILD_OK',bundle,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--rebuild',action='store_true')
    args=parser.parse_args();build(args.output,args.rebuild)
