"""Independent full-array PLY/USD and contract assembly verification, CPU only."""
import argparse
from pathlib import Path
import traceback
import numpy as np
from usd_environment import initialize
initialize()
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics
from contract_math import ROOT, load_config, sha256, write_json, points


def read_raw_ply(path):
    # All five pinned inputs use binary little-endian, scalar float vertex fields.
    with Path(path).open('rb') as stream:
        assert stream.readline().strip()==b'ply';fields=[];count=None
        while True:
            line=stream.readline().decode('ascii').strip()
            if line.startswith('format '):assert line=='format binary_little_endian 1.0'
            if line.startswith('element '):
                _,element,n=line.split();assert element=='vertex';count=int(n)
            if line.startswith('property '):
                _,kind,name=line.split();assert kind=='float';fields.append((name,'<f4'))
            if line=='end_header':break
            if not line:raise ValueError('Unexpected EOF')
        data=np.fromfile(stream,dtype=np.dtype(fields),count=count)
    assert len(data)==count
    return data


def max_error(actual,expected,limit,label):
    assert np.shape(actual)==np.shape(expected),(label,np.shape(actual),np.shape(expected))
    value=float(np.max(np.abs(np.asarray(actual)-expected)))
    assert value<=limit,(label,value,limit)
    return value


def validate(bundle=None):
    cfg=load_config();bundle=Path(bundle or ROOT/'assets'/cfg['asset_name'])
    result={'passed':False,'asset_manifest_sha256':sha256(bundle/'manifest.json'),'parts':{},'joints':[]}
    write_json(ROOT/'reports/geometry_validation.json',result)
    try:
        stage=Usd.Stage.Open(str(bundle/(cfg['asset_name']+'.usda')))
        assert UsdGeom.GetStageUpAxis(stage)=='Z' and UsdGeom.GetStageMetersPerUnit(stage)==1
        # Independent published contract matrix (rounded in the supplied document).
        doc=np.array([[1.147150821,.619949408,-2.014871640,3.203520],
                      [2.094579558,-.075904550,1.169177049,-.342170],
                      [.238288623,-2.317304734,-.577336385,2.049340],[0,0,0,1]])
        bind={'track_link':[0,0,0],'swing_link':[0,0,.6],
              'boom_link':[-.374,-.270,1.554],'arm_link':[4.176,-.336,4.752],
              'bucket_link':[5.402,-.429,2.090]}
        for part in cfg['parts']:
            raw=read_raw_ply(ROOT/'sources/ply'/part['ply']);assert len(raw)==part['count']
            body=stage.GetPrimAtPath('/Excavator/'+part['frame']);prim=stage.GetPrimAtPath(str(body.GetPath())+'/Visuals/Splat')
            get=lambda name:np.asarray(prim.GetAttribute(name).Get())
            xyz=np.column_stack([raw[x] for x in ['x','y','z']])
            pos=get('positions');report={'count':len(raw)}
            report['raw_center_max_error']=max_error(pos,xyz,0,'raw coordinates')
            scale=np.exp(np.column_stack([raw['scale_'+str(k)] for k in range(3)]).astype(float)).astype(np.float32)
            report['linear_scale_max_error']=max_error(get('scales'),scale,2e-6,'log scale decoding')
            expected_opacity=(1/(1+np.exp(-raw['opacity'].astype(float)))).astype(np.float32)
            report['opacity_max_error']=max_error(get('opacities'),expected_opacity,2e-7,'opacity decoding')
            q=np.column_stack([raw['rot_'+str(k)] for k in range(4)]).astype(float);q/=np.linalg.norm(q,axis=1)[:,None]
            q_usd=np.array([[x.GetReal(),*x.GetImaginary()] for x in prim.GetAttribute('orientations').Get()])
            report['quaternion_max_error']=max_error(q_usd,q,4e-7,'quaternion wxyz')
            dc=np.column_stack([raw['f_dc_'+str(k)] for k in range(3)])
            rest=np.column_stack([raw['f_rest_'+str(k)] for k in range(45)]).reshape(-1,3,15).transpose(0,2,1)
            sh=np.concatenate([dc[:,None,:],rest],axis=1).reshape(-1,3)
            report['sh_max_error']=max_error(get('radiance:sphericalHarmonicsCoefficients'),sh,0,'SH channel ordering')
            assert prim.GetAttribute('radiance:sphericalHarmonicsDegree').Get()==3
            mat=np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
            report['bind_center_max_error_m']=max_error(points(mat,pos),points(doc,xyz),2e-6,'bind geometry')
            bmat=np.array(UsdGeom.Xformable(body).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
            expected=np.eye(4);expected[:3,3]=bind[part['frame']]
            report['bind_frame_max_error']=max_error(bmat,expected,1e-12,'bind frame')
            # A linear transform applies equally to Gaussian centers and covariance axes.
            report['linear_model_max_error']=max_error(mat[:3,:3],doc[:3,:3],3e-7,'Gaussian axis transform')
            assert body.HasAPI(UsdPhysics.RigidBodyAPI)
            result['parts'][part['id']]=report
            print('VERIFIED',part['id'],report['bind_center_max_error_m'],flush=True)
        for j in cfg['joints']:
            native=UsdPhysics.RevoluteJoint(stage.GetPrimAtPath('/Excavator/Joints/'+j['name']))
            assert native.GetAxisAttr().Get()==j['axis']
            assert list(native.GetBody0Rel().GetTargets())==[Sdf.Path('/Excavator/'+j['parent_body'])]
            assert list(native.GetBody1Rel().GetTargets())==[Sdf.Path('/Excavator/'+j['child_frame'])]
            max_error(np.array(native.GetLocalPos0Attr().Get()),np.array(j['xyz_m']),3e-7,'joint center')
            max_error(np.array(native.GetLocalPos1Attr().Get()),np.zeros(3),0,'child center')
            for getter in [native.GetLocalRot0Attr,native.GetLocalRot1Attr]:assert getter().Get()==Gf.Quatf(1)
            # Joint anchor equality in the actual composed USD bind transforms.
            p0=stage.GetPrimAtPath('/Excavator/'+j['parent_body']);p1=stage.GetPrimAtPath('/Excavator/'+j['child_frame'])
            a=UsdGeom.Xformable(p0).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).Transform(Gf.Vec3d(*native.GetLocalPos0Attr().Get()))
            b=UsdGeom.Xformable(p1).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).Transform(Gf.Vec3d(*native.GetLocalPos1Attr().Get()))
            error=float(np.linalg.norm(np.array(a)-np.array(b)));assert error<5e-7
            result['joints'].append({'name':j['name'],'axis':j['axis'],'anchor_error_m':error})
        assert sum(p.GetTypeName()=='ParticleField3DGaussianSplat' for p in stage.Traverse())==5
        assert sum(p.HasAPI(UsdPhysics.ArticulationRootAPI) for p in stage.Traverse())==1
        assert not any(p.HasAPI(UsdPhysics.CollisionAPI) for p in stage.Traverse())
        for layer in stage.GetUsedLayers():
            if not layer.anonymous:assert Path(layer.realPath).resolve().is_relative_to(bundle.resolve()),layer.realPath
        result.update(passed=True,total_gaussians=sum(p['count'] for p in cfg['parts']),
                      scope='All Gaussian arrays and zero-pose USD transforms checked; native motion checked separately in Isaac')
    except Exception:
        result['error']=traceback.format_exc();raise
    finally:write_json(ROOT/'reports/geometry_validation.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path)
    print('GEOMETRY_VALIDATION',validate(p.parse_args().bundle)['passed'])
