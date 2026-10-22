"""GUI integration acceptance: own Kit process, private DDS domain, no asset saves."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
import numpy as np
import omni.kit.app
import omni.usd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/fisheye_motion'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
SCENE=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_14_fisheye.usda')
OLD=SCENE.with_name('combine_scene_13_3dgs_contract.usda')


async def main():
    app=omni.kit.app.get_app()
    manager=None
    report={'passed':False,'status':'starting','domain':138}
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SCENE,OLD)}
    (OUT/'result.json').write_text(json.dumps(report))
    try:
        from sensor_visualizer.config import load_config
        from sensor_visualizer.session import SceneSession
        assert (await omni.usd.get_context().open_stage_async(str(SCENE)))[0]
        for _ in range(12): await app.next_update_async()
        cfg=load_config(ROOT/'config/sensors.json')
        cfg['ros_domain_id']=138
        cfg['output_directory']=str(OUT/'recordings')
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=True)
        await manager.refresh()
        r=manager.instance
        assert r is not None,manager.error
        print('FISHEYE_INITIALIZED',flush=True)
        r.timeline.play()
        for i in range(80):
            await app.next_update_async()
            if r.camera.error: raise AssertionError(r.camera.error)
            if r.camera.latest is not None and r.motion.ready: break
        else:
            raise AssertionError(f'No matched image: received={r.camera.received} unmatched={r.camera.unmatched} history={list(r.camera.history)[-8:]}')
        assert len(r.config['sensors'])==13
        report['scan_types']={s['id']:s['scan_type'] for s in r.config['sensors']}
        report['camera_model']=r.camera.latest[1]['lens_distortion_model']
        print('FISHEYE_FIRST_MATCH',report['camera_model'],flush=True)
        r.camera.preview()
        initial=dict(r.motion.last_snapshot)
        c=r.motion.base_controller
        r.motion.command_base('direct',x=c.x+.2,y=c.y-.1,yaw_deg=math.degrees(c.heading)+15)
        for _ in range(3): await app.next_update_async()
        p=np.array(r.motion.last_snapshot['root_position'])
        assert np.linalg.norm(p-np.array(initial['root_position'])-[.2,-.1,0])<1e-4
        orientation=list(r.motion.last_snapshot['root_xyzw'])
        joint=r.config['robot_motion']['joints'][0]['name']
        current=r.motion.actual_degrees()[joint]
        r.motion.command('execute',commands={joint:{'mode':'direct','target':current+2,
            'speed':5,'lower':current-15,'upper':current+15}})
        for _ in range(3): await app.next_update_async()
        assert abs(np.dot(orientation,r.motion.last_snapshot['root_xyzw']))>1-1e-5
        session=await r.start_recording([s['id'] for s in r.config['sensors']])
        report['recording']=str(session)
        r.motion.command_base('velocity',speed=.2,yaw_rate_deg=10)
        for i in range(65):
            if i==35:
                r.motion.command_base('velocity',speed=-.2,yaw_rate_deg=-10)
            await app.next_update_async()
            if r.camera.error: raise AssertionError(r.camera.error)
        r.motion.command_base('hold')
        await r.stop_recording()
        assert r.camera.count>=8,r.camera.count
        report['images_saved']=r.camera.count
        report['received']=r.camera.received
        report['unmatched']=r.camera.unmatched
        report['cloud_counts']={s:gate.published for s,gate in r.cloud_publishers.stats.items()}
        assert all(v>=5 for v in report['cloud_counts'].values()),report['cloud_counts']
        report['snapshot']=str(r.camera.snapshot())
        r.timeline.pause()
        position=np.array(r.motion.last_snapshot['root_position'])
        for _ in range(5): await app.next_update_async()
        assert np.linalg.norm(np.array(r.motion.last_snapshot['root_position'])-position)<1e-6
        r.motion.command_base('reset')
        assert np.linalg.norm(r.motion.articulation.get_world_poses()[0].numpy()[0]-r.motion.initial_position)<1e-4
        r.timeline.stop()
        await manager.close()
        manager=None
        # Re-run without reopening the asset: detect orphaned graphs/annotators.
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=False)
        await manager.refresh()
        assert manager.instance is not None,manager.error
        manager.instance.timeline.play()
        for _ in range(18): await app.next_update_async()
        assert manager.instance.camera.latest is not None
        report['rerun_passed']=True
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
        report['scene_hashes_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        report['scene_sha256']=hashes
        report['passed'] = report['passed'] and report['scene_hashes_unchanged']
        (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print('FISHEYE_RESULT',report['passed'],flush=True)
        app.post_quit(0 if report['passed'] else 1)


_task=asyncio.ensure_future(main())
