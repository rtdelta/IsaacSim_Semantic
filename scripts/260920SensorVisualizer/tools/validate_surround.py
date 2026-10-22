"""Full GUI acceptance in a dedicated Kit process and private ROS domain 139."""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
import numpy as np
import omni.kit.app
import omni.usd
from pxr import Usd,UsdGeom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/surround_fisheye'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
ASSETS=Path('/root/gpufree-data/IsaacSim_Asset')
SCENE=ASSETS/'combine_stage/combine_scene_15_surround_fisheye.usda'
SOURCE=ASSETS/'sensor_set/camera_set/fish_eye_camera/fish_eye_camera.usda'


async def main():
    app=omni.kit.app.get_app();manager=None
    report={'passed':False,'status':'starting','domain':139}
    files=[SCENE,SOURCE,*[ASSETS/f'combine_stage/{name}' for name in (
        'combine_scene_13_3dgs_contract.usda','combine_scene_14_fisheye.usda')]]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (OUT/'result.json').write_text(json.dumps(report))
    try:
        from sensor_visualizer.config import load_config
        from sensor_visualizer.session import SceneSession
        cfg=load_config(ROOT/'config/sensors.json');cfg['ros_domain_id']=139
        cfg['output_directory']=str(OUT/'recordings')
        assert (await omni.usd.get_context().open_stage_async(str(SCENE)))[0]
        for _ in range(12): await app.next_update_async()
        stage=omni.usd.get_context().get_stage()
        source=Usd.Stage.Open(str(SOURCE));src=source.GetPrimAtPath('/World/FisheyeCamera')
        placement={}
        for c in cfg['cameras']:
            camera=stage.GetPrimAtPath(c['prim_path'])
            assert camera.GetAttribute('aif:lidarToCamera').Get() is None
            for a in src.GetAttributes():
                if a.GetName().startswith(('omni:lensdistortion:','exposure:')):
                    assert camera.GetAttribute(a.GetName()).Get()==a.Get(),a.GetName()
            cache=UsdGeom.XformCache()
            cam=cache.GetLocalToWorldTransform(camera)
            sensor=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(c['position_source']))
            error=(cam.ExtractTranslation()-sensor.ExtractTranslation()).GetLength()
            assert error<1e-7
            assert abs(cam.GetDeterminant()-1)<1e-6
            placement[c['id']]={'origin_error_m':error,'rigid_transform':True}
        report['placement']=placement
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=True)
        await manager.refresh();r=manager.instance
        assert r is not None,manager.error
        assert len(r.camera.cameras)==4
        print('SURROUND_INITIALIZED',flush=True)
        r.timeline.play()
        for _ in range(100):
            await app.next_update_async()
            assert not r.camera.error,r.camera.error
            if r.camera.latest is not None: break
        else: raise AssertionError('No complete camera group')
        r.camera.preview('front')
        report['initial_snapshot']=str(r.camera.snapshot())
        report['image_stats']={}
        for cid,c in r.camera.cameras.items():
            rgb=c.latest[0][:,:,:3]
            assert rgb.shape==(1080,1920,3),(cid,rgb.shape)
            std=float(rgb.std());bright=float((rgb.max(axis=2)>20).mean())
            report['image_stats'][cid]={'std':std,'nonblack_fraction':bright}
            assert std>5 and bright>.2,(cid,report['image_stats'][cid])
        session=await r.start_recording([s['id'] for s in r.config['sensors']])
        report['recording']=str(session)
        r.motion.command_base('velocity',speed=.15,yaw_rate_deg=8)
        for i in range(66):
            if i==33: r.motion.command_base('velocity',speed=-.1,yaw_rate_deg=-8)
            await app.next_update_async()
            assert not r.camera.error,r.camera.error
        r.motion.command_base('hold')
        await r.stop_recording()
        report['saved_groups']=r.camera.count
        report['saved_per_camera']={cid:c.count for cid,c in r.camera.cameras.items()}
        report['dropped_groups']=r.camera.dropped
        report['unmatched_images']=r.camera.unmatched
        assert r.camera.count>=8
        assert all(c.count==r.camera.count for c in r.camera.cameras.values())
        assert not r.camera.dropped,r.camera.dropped
        r.timeline.pause()
        latest=r.camera.latest[0]
        for _ in range(5): await app.next_update_async()
        assert r.camera.latest[0]==latest
        r.motion.command_base('reset')
        r.timeline.stop()
        await manager.close();manager=None
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=False)
        await manager.refresh();assert manager.instance,manager.error
        manager.instance.timeline.play()
        for _ in range(20): await app.next_update_async()
        assert manager.instance.camera.latest is not None
        report['rerun_passed']=True
        await manager.close();manager=None
        # Legacy single-camera scene must remain usable with the new project config.
        assert (await omni.usd.get_context().open_stage_async(str(files[-1])))[0]
        for _ in range(8): await app.next_update_async()
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=False)
        await manager.refresh();assert manager.instance,manager.error
        assert not hasattr(manager.instance.camera,'cameras')
        manager.instance.timeline.play()
        for _ in range(18): await app.next_update_async()
        assert manager.instance.camera.latest is not None
        report['scene14_compatible']=True
        report.update(passed=True,status='complete')
    except Exception:
        report.update(passed=False,status='failed',error=traceback.format_exc())
        print(report['error'],flush=True)
    finally:
        if manager:
            try: await manager.close()
            except Exception: report.update(passed=False,cleanup_error=traceback.format_exc())
        try: await omni.usd.get_context().close_stage_async()
        except Exception: report.update(passed=False,stage_close_error=traceback.format_exc())
        report['asset_hashes_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        report['asset_sha256']=hashes
        report['passed']=report['passed'] and report['asset_hashes_unchanged']
        (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print('SURROUND_RESULT',report['passed'],flush=True)
        app.post_quit(0 if report['passed'] else 1)


_task=asyncio.ensure_future(main())
