"""Native recording and official IMU probes in disposable, fully composed scenes."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.contracts import DEFAULT,write_json


async def main():
    import omni.kit.app,omni.usd,omni.timeline,carb.settings
    import numpy as np
    from pxr import Usd,UsdGeom,UsdPhysics,UsdRender,Gf,PhysxSchema
    from single0602_headless.interactive_runtime import InteractiveRuntime
    from single0602_headless.imu_interface import ImuProbeDriver,ros_imu_fields
    from isaacsim.sensors.experimental.physics import IMU
    from single0602_headless.launch_config import resolve_interactive_job,snapshot_launch
    app=omni.kit.app.get_app()
    out=Path(os.environ.get('S0602_BINDING_OUTPUT','/root/gpufree-data/semantic/output/s06binding'))
    out.mkdir(parents=True,exist_ok=True)
    report={'state':'running','output':str(out),'cases':[]};owner=None;drivers=[]
    def save():write_json(ROOT/'reports/scene_binding_native.json',report)
    def command(action,payload=None):
        return owner.command({'action':action,'payload':payload or {},'command_id':uuid.uuid4().hex})
    save()
    try:
        source=Path(DEFAULT['scene'])
        report['source_scene_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        initial=re.sub(r'@([^@]+)@',lambda m:'@'+str((source.parent/m.group(1)).resolve())+'@'
            if not m.group(1).startswith('/') and '://' not in m.group(1) else m.group(0),source.read_text())
        reference_lidar='/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/MyAiry/MyAiry.usda'
        fixtures={}
        for name in ('baseline','zero','camera_only','lidar_only','mixed','renamed'):
            path=out/(name+'.usda');text=initial
            path.write_text(text,encoding='utf-8')
            stage=Usd.Stage.Open(str(path))
            if name=='renamed':
                # A composed reference remaps internal relationships; renaming only
                # the root text would leave the actual robot in weaker sublayers.
                old=stage.GetPrimAtPath('/World/Excavator');assert old
                new=stage.DefinePrim('/World/NewMachine','Xform')
                new.GetReferences().AddReference(str(source),'/World/Excavator')
                old.SetActive(False)
            domes=[p for p in stage.Traverse() if p.GetTypeName()=='DomeLight']
            preferred=stage.GetPrimAtPath('/environment_Fangshan_02/DomeLight')
            chosen=str(preferred.GetPath()) if preferred else (str(domes[0].GetPath()) if domes else None)
            for dome in domes:
                if str(dome.GetPath())!=chosen:dome.SetActive(False)
            root='/World/NewMachine' if name=='renamed' else '/World/Excavator'
            assert stage.GetPrimAtPath(root),root
            original_sensors=[p for p in stage.Traverse() if str(p.GetTypeName()) in ('Camera','OmniLidar')]
            # Fixture products are retired explicitly, including zero-sensor cases.
            for prim in list(stage.Traverse()):
                if prim.IsA(UsdRender.Product):prim.SetActive(False)
                attr=prim.GetAttribute('node:type')
                if attr and attr.Get()=='isaacsim.core.nodes.IsaacCreateRenderProduct':
                    enabled=prim.GetAttribute('inputs:enabled')
                    if enabled:enabled.Set(False)
            if name not in ('baseline','mixed'):
                for prim in original_sensors:prim.SetActive(False)
            if name=='mixed':
                camera_kept=lidar_kept=False
                for prim in original_sensors:
                    if prim.GetTypeName()=='Camera' and str(prim.GetPath()).startswith(root+'/') and not camera_kept:camera_kept=True;continue
                    if prim.GetTypeName()=='OmniLidar' and not lidar_kept:lidar_kept=True;continue
                    prim.SetActive(False)
            if name in ('camera_only','mixed','renamed'):
                camera=UsdGeom.Camera.Define(stage,'/Station/Observation')
                cache=UsdGeom.XformCache();center=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(root+'/track_link')).ExtractTranslation()+Gf.Vec3d(0,0,2)
                eye=center+Gf.Vec3d(10,-12,9)
                matrix=Gf.Matrix4d().SetLookAt(eye,center,Gf.Vec3d(0,0,1)).GetInverse()
                camera.AddTransformOp().Set(matrix)
                camera.GetFocalLengthAttr().Set(24)
                camera.GetClippingRangeAttr().Set(Gf.Vec2f(.1,10000))
            if name in ('lidar_only','mixed'):
                lidar=stage.DefinePrim('/Station/RangeRig','Xform');lidar.GetReferences().AddReference(reference_lidar)
                UsdGeom.Xformable(lidar).AddTranslateOp().Set(Gf.Vec3d(0,0,3))
            if name=='mixed':
                with Usd.EditContext(stage):
                    imu_prim=stage.DefinePrim(root+'/boom_link/OfficialImu','IsaacImuSensor')
                    # Native schema candidate; the separate official factory probe below validates real reads.
                    imu_prim.SetCustomDataByKey('validation_origin','official_native_IMU_authoring')
                camera=UsdGeom.Camera.Define(stage,root+'/RootEye')
                camera.AddTranslateOp().Set(Gf.Vec3d(0,-7,6))
                camera.AddRotateXYZOp().Set(Gf.Vec3f(55,0,0))
            stage.GetRootLayer().Save();fixtures[name]=str(path);stage=None
        report['fixtures']=fixtures;save()
        for name,path in fixtures.items():
            job,info=resolve_interactive_job(ROOT,scene=path,output=str(out),check_files=True)
            job['sensors']['camera_resolution']=[320,240]
            jobpath,job=snapshot_launch(job,info)
            owner=InteractiveRuntime(ROOT,job_path=jobpath,socket_path='/tmp/s06bind_'+uuid.uuid4().hex+'.sock')
            await owner.initialize(open_scene=True)
            case={'name':name,'scene':path,'launch_job':str(jobpath),'binding':owner.scene.binding_report,
                  'registry':owner.scene.registry}
            if name=='zero':assert not owner.scene.registry['cameras'] and not owner.scene.registry['lidars']
            if name=='baseline':
                assert {'front','back','left','right'}.issubset({r['id'] for r in owner.scene.registry['cameras']})
                assert len(owner.scene.registry['lidars'])==13
            if name in ('camera_only','renamed'):assert len(owner.scene.registry['cameras'])==1 and not owner.scene.registry['lidars']
            if name=='lidar_only':assert len(owner.scene.registry['lidars'])==1 and not owner.scene.registry['cameras']
            car_driver=None;car_samples=[]
            if name=='mixed':
                car_driver=ImuProbeDriver('/World/Excavator/boom_link/OfficialImu','car_imu')
                car_driver.initialize();drivers.append(car_driver)
            start=command('record_start');command('motion',{'base':{'speed_m_s':.2,'yaw_rate_deg_s':2}})
            command('play');deadline=time.monotonic()+40
            while owner.time_s<.35:
                if owner.failed:raise RuntimeError(owner.error)
                if time.monotonic()>deadline:raise TimeoutError('Recording did not advance: '+name)
                await app.next_update_async()
                if car_driver:
                    value=car_driver.read()
                    if value['is_valid'] and value['status']=='valid':car_samples.append(value)
            command('pause');command('record_stop')
            while owner.drains:await app.next_update_async()
            assert not owner.trajectory_error,owner.trajectory_error
            case['trajectory']=start['path']
            case['duration_s']=owner.time_s
            if car_driver:
                case['imu_valid_samples']=len(car_samples)
                assert len(car_samples)>=3,'Official IMU on the excavator produced no valid samples'
                car_driver.close()
            report['cases'].append(case);save()
            await owner.close();owner=None
        # The official factory generates a self-contained native IMU fixture.
        await omni.usd.get_context().new_stage_async()
        stage=omni.usd.get_context().get_stage()
        physics=UsdPhysics.Scene.Define(stage,'/World/PhysicsScene')
        physics.CreateGravityDirectionAttr().Set(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr().Set(9.81)
        cube=UsdGeom.Cube.Define(stage,'/World/OfficialBody');cube.GetSizeAttr().Set(1.)
        rigid=UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim())
        PhysxSchema.PhysxRigidBodyAPI.Apply(cube.GetPrim()).CreateDisableGravityAttr().Set(True)
        IMU.create('/World/OfficialBody/Device',translations=np.array([[0.,0.,0.]]),
                   orientations=np.array([[1.,0.,0.,0.]]),linear_acceleration_filter_size=1,
                   angular_velocity_filter_size=1,orientation_filter_size=1)
        stage.GetRootLayer().Export(str(out/'official_imu_fixture.usda'))
        timeline=omni.timeline.get_timeline_interface()
        settings=carb.settings.get_settings()
        settings.set('/app/player/useFixedTimeStepping',True)
        settings.set('/app/runLoops/main/rateLimitEnabled',False)
        timeline.set_target_framerate(60);timeline.set_auto_update(True)
        driver=ImuProbeDriver('/World/OfficialBody/Device','official_imu');driver.initialize();drivers.append(driver)
        timeline.play();timeline.commit()
        samples=[];without=[];deadline=time.monotonic()+90
        while not samples or samples[-1]['sensor_time_s']-samples[0]['sensor_time_s']<5.:
            if time.monotonic()>deadline:raise TimeoutError('Official IMU did not supply five seconds of valid data')
            await app.next_update_async()
            value=driver.read()
            if value['is_valid'] and value['status']=='valid':
                samples.append(value)
                driver.read_gravity=False;without.append(driver.read());driver.read_gravity=True
        assert max(abs(v) for r in samples[-60:] for v in r['angular_velocity_rad_s'])<1e-3
        assert abs(np.linalg.norm(samples[-1]['linear_acceleration_m_s2'])-9.81)<.05
        assert np.linalg.norm(without[-1]['linear_acceleration_m_s2'])<.05
        mapped=ros_imu_fields(samples[-1]);assert mapped['stamp_ns']==round(samples[-1]['sensor_time_s']*1e9)
        duplicate=driver.read();assert duplicate['status']=='repeated_physics_sample'
        timeline.stop();timeline.commit();await app.next_update_async();driver.close()
        rotated=UsdGeom.Xformable(stage.GetPrimAtPath('/World/OfficialBody/Device'))
        # Recreate through the official wrapper while stopped; no production asset is edited.
        IMU('/World/OfficialBody/Device',orientations=np.array([[math.sqrt(.5),math.sqrt(.5),0.,0.]]))
        driver.initialize();timeline.play();timeline.commit()
        rotated_sample=None
        for _ in range(30):
            await app.next_update_async();value=driver.read()
            if value['is_valid']:rotated_sample=value
        assert rotated_sample and abs(rotated_sample['linear_acceleration_m_s2'][1])>9.7
        timeline.stop();timeline.commit();await app.next_update_async();driver.close()
        rigid.CreateAngularVelocityAttr().Set(Gf.Vec3f(0,0,45))
        driver.initialize();timeline.play();timeline.commit();motion_samples=[]
        for _ in range(60):
            await app.next_update_async();value=driver.read()
            if value['is_valid']:motion_samples.append(value)
        assert motion_samples and max(np.linalg.norm(s['angular_velocity_rad_s']) for s in motion_samples)>.5
        timeline.stop();timeline.commit();await app.next_update_async();driver.close()
        write_json(out/'imu_samples.json',{'with_gravity':samples,'without_gravity':without,'rotated':rotated_sample,'motion':motion_samples})
        report['imu']={'passed':True,'factory':'isaacsim.sensors.experimental.physics.IMU.create',
            'fixture':str(out/'official_imu_fixture.usda'),'api':driver.api,'samples':len(samples),
            'duration_s':samples[-1]['sensor_time_s']-samples[0]['sensor_time_s'],
            'gravity_last':samples[-1]['linear_acceleration_m_s2'],'without_gravity_last':without[-1]['linear_acceleration_m_s2'],
            'rotated':rotated_sample,'motion_samples':len(motion_samples),'formal_capture_supported':False}
        assert hashlib.sha256(source.read_bytes()).hexdigest()==report['source_scene_sha256']
        report['state']='passed'
    except Exception:
        report.update(state='failed',error=traceback.format_exc())
    finally:
        for driver in drivers:driver.close()
        if owner:
            try:await owner.close()
            except Exception:report['cleanup_error']=traceback.format_exc()
        save();print('SCENE_BINDING_NATIVE='+json.dumps(report),flush=True)
        app.post_quit(0 if report['state']=='passed' else 1)


task=asyncio.ensure_future(main())
