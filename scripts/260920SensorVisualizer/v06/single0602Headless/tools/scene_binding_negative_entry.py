"""Reject incompatible initial assets before creating sensor products."""
import asyncio,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from single0602_headless.contracts import load_job,write_json


async def main():
    import omni.kit.app
    from pxr import Usd,UsdPhysics,UsdGeom
    from single0602_headless.scene import SceneStepper
    native=json.loads((ROOT/'reports/scene_binding_native.json').read_text())
    out=Path(native['output']);source=Path(native['fixtures']['camera_only'])
    report={'state':'running','cases':[]};scene=None
    try:
        cases=[]
        for name in ('bad_axis','bad_camera','two_robots','no_robot'):
            path=out/(name+'.usda');path.write_bytes(source.read_bytes());stage=Usd.Stage.Open(str(path))
            options={}
            if name=='bad_axis':
                UsdPhysics.RevoluteJoint(stage.GetPrimAtPath('/World/Excavator/Joints/boom')).GetAxisAttr().Set('X')
                expected='excavator.joints.boom.axis'
            elif name=='bad_camera':
                UsdGeom.Camera(stage.GetPrimAtPath('/Station/Observation')).GetFocalLengthAttr().Set(-1.)
                options={'sensors':{'camera_ids':['Observation']}};expected='Invalid camera focal length'
            elif name=='two_robots':
                prim=stage.DefinePrim('/World/OtherMachine','Xform')
                prim.GetReferences().AddReference(native['fixtures']['baseline'],'/World/Excavator')
                expected='Expected one supported excavator'
            else:
                stage.GetPrimAtPath('/World/Excavator').SetActive(False)
                expected='Expected one supported excavator'
            stage.GetRootLayer().Save();stage=None;cases.append((name,path,options,expected))
        for name,path,options,expected in cases:
            job=load_job(overrides={'scene':str(path),'output_directory':str(out),'render':{'background_dome':None},**options})
            scene=SceneStepper(ROOT,job)
            try:
                await scene.initialize(sensor_products=True)
            except (ValueError,RuntimeError) as exc:
                assert expected in str(exc),(name,str(exc))
                assert scene.drivers is None,'Invalid asset created capture products'
                report['cases'].append({'name':name,'passed':True,'error':str(exc),'products_created':False})
            else:raise AssertionError('Incompatible asset admitted: '+name)
            await scene.close();scene=None
        report['state']='passed'
    except Exception:report.update(state='failed',error=traceback.format_exc())
    finally:
        if scene:
            try:await scene.close()
            except Exception:report['cleanup_error']=traceback.format_exc()
        write_json(ROOT/'reports/scene_binding_negative.json',report)
        print('SCENE_BINDING_NEGATIVE='+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_quit(0 if report['state']=='passed' else 1)


task=asyncio.ensure_future(main())
