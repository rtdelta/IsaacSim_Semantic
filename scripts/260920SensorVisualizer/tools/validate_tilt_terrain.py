"""Independent GUI acceptance for scene16, using ROS domain 141 and test output."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import traceback
import numpy as np
import omni.kit.app
import omni.usd
from pxr import Gf, UsdGeom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/tilt_terrain'
ASSETS=Path('/root/gpufree-data/IsaacSim_Asset')
SCENE=ASSETS/'combine_stage/combine_scene_16_terrain_fisheye.usda'
sys.path.insert(0,str(ROOT))


def rows(m):return [[float(m[i][j]) for j in range(4)] for i in range(4)]


async def main():
    app=omni.kit.app.get_app();manager=None
    report={'passed':False,'status':'starting','domain':141,'checks':{}}
    paths=[ASSETS/'combine_stage/combine_scene_15_surround_fisheye.usda',SCENE,
           ASSETS/'sensor_set/camera_set/fish_eye_camera/fish_eye_camera.usda']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    def save(): (OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    async def advance(n,r):
        for _ in range(n):
            await app.next_update_async()
            assert not r.motion.failed,'Motion controller failed'
            assert not r.camera.error,r.camera.error
    def check(name,condition):
        report['checks'][name]=bool(condition)
        assert condition,name
        save()
    try:
        from sensor_visualizer.config import load_config
        from sensor_visualizer.session import SceneSession
        cfg=load_config(ROOT/'config/sensors.json');cfg['ros_domain_id']=141
        cfg['output_directory']=str(OUT/'recordings')
        save()
        assert (await omni.usd.get_context().open_stage_async(str(SCENE)))[0]
        for _ in range(12):await app.next_update_async()
        stage=omni.usd.get_context().get_stage()
        terrain=stage.GetPrimAtPath('/World/UndulatingGround')
        check('terrain_present',bool(terrain))
        for path in ['/FlatGrid/Environment/Geometry','/FlatGrid/GroundPlane/CollisionPlane']:
            check('available_'+path,bool(stage.GetPrimAtPath(path)))
        check('original_3dgs_ground_available',stage.GetPrimAtPath('/environment_Fangshan_02/changjing4').IsActive())
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=True)
        await manager.refresh();r=manager.instance
        assert r is not None,manager.error
        check('four_camera_rig',len(r.camera.cameras)==4)
        check('tilt_panel_created',hasattr(r.base_panel,'tilt_panel'))
        r.timeline.play()
        for _ in range(120):
            await advance(1,r)
            if r.camera.latest is not None and r.motion.ready:break
        else:raise AssertionError('No complete camera group')
        await advance(8,r)
        check('all_lidars_publish_before_recording',all(g.published>0 for g in r.cloud_publishers.stats.values()))
        report['initial_snapshot']=str(r.camera.snapshot());report['status']='testing_pose';save()
        c=r.motion.base_controller;initial=c.snapshot()
        baseline_ref=r.motion.initial_reference
        sensor_paths=[s['prim_path'] for s in r.config['sensors']]+[v['prim_path'] for v in cfg['cameras']]
        cache=UsdGeom.XformCache()
        relative={p:cache.GetLocalToWorldTransform(stage.GetPrimAtPath(p))*baseline_ref.GetInverse() for p in sensor_paths}
        r.timeline.pause();await app.next_update_async()
        r.motion.command_base('height',z=c.initial[2]+.35)
        r.motion.command_tilt('execute',commands={'pitch':{'mode':'direct','target':10},'roll':{'mode':'direct','target':-7}})
        snap=r.motion.snapshot(r.timeline.get_current_time())
        expected=r.motion._root_matrix(c.position,c.orientation)
        actual=r.motion._root_matrix(snap['root_position'],[snap['root_xyzw'][3],*snap['root_xyzw'][:3]])
        pose_error=float(np.max(np.abs(np.array(rows(expected))-np.array(rows(actual)))))
        report['direct_pose_error']=pose_error
        check('paused_direct_xyz_pitch_roll',pose_error<2e-5)
        check('height_is_manual',abs(snap['root_position'][2]-c.initial[2]-.35)<2e-5)
        cache=UsdGeom.XformCache();relative_error=0.
        for p,m in relative.items():
            current=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(p))*actual.GetInverse()
            relative_error=max(relative_error,float(np.max(np.abs(np.array(rows(current))-np.array(rows(m))))))
        report['sensor_mount_matrix_error']=relative_error
        check('all_sensor_mounts_rigid',relative_error<3e-5)
        # Exercise the public panel callbacks, not only the motion classes.
        panel=r.base_panel.tilt_panel
        for name,value,speed in [('pitch',4,60),('roll',3,50)]:
            row=panel.rows[name];row['mode'].model.get_item_value_model().set_value(1)
            row['target'].set_value(value);row['speed'].set_value(speed);panel.execute(name)
        r.timeline.play();await advance(30,r)
        check('target_mode_finishes',all(not s.running for s in c.tilt.states.values()))
        check('target_angles',abs(c.tilt_angles()['pitch']-4)<1e-4 and abs(c.tilt_angles()['roll']-3)<1e-4)
        for name,speed in [('pitch',40),('roll',30)]:
            row=panel.rows[name];row['mode'].model.get_item_value_model().set_value(2)
            row['lower'].set_value(-4);row['upper'].set_value(4);row['speed'].set_value(speed)
        panel.execute_all()
        r.motion.command_base('velocity',speed=.12,yaw_rate_deg=4)
        r.motion.command('execute',commands={r.motion.config['joints'][0]['name']:
            {'mode':'target','target':3,'speed':10}})
        session=await r.start_recording([s['id'] for s in r.config['sensors']])
        report['recording']=str(session);report['status']='recording';save()
        samples=[]
        for _ in range(72):
            await advance(1,r);samples.append(c.tilt_angles())
        r.motion.command_base('hold');r.motion.command('hold')
        await r.stop_recording()
        report['final_snapshot']=str(r.camera.snapshot())
        report['groups']=r.camera.count;report['dropped']=r.camera.dropped
        report['cloud_gates']={sid:dict(vars(g)) for sid,g in r.cloud_publishers.stats.items()}
        check('all_lidars_publish_after_tilting',all(g.published>=12 for g in r.cloud_publishers.stats.values()))
        report['unmatched_images']=r.camera.unmatched
        check('periodic_pitch_moves',max(s['pitch'] for s in samples)-min(s['pitch'] for s in samples)>5)
        check('periodic_roll_moves',max(s['roll'] for s in samples)-min(s['roll'] for s in samples)>5)
        check('periodic_bounds',all(-4.0001<=s[n]<=4.0001 for s in samples for n in ('pitch','roll')))
        check('hold_base_stops_all',not c.speed and not c.yaw_rate and all(not s.running for s in c.tilt.states.values()))
        check('manual_z_stays_constant',abs(c.z-initial['position_world_m'][2]-.35)<1e-6)
        check('recorded_complete_groups',r.camera.count>=8 and not r.camera.dropped and not r.camera.unmatched)
        r.timeline.pause();await app.next_update_async()
        before=c.snapshot();await advance(4,r)
        check('pause_holds_pose',c.snapshot()==before)
        r.motion.command_base('reset')
        check('reset_base',np.allclose(c.position,c.initial[:3]) and c.tilt_angles()=={'pitch':0.,'roll':0.})
        r.timeline.stop();await app.next_update_async()
        check('stop_clears_tilt',c.tilt_angles()=={'pitch':0.,'roll':0.})
        await manager.close();manager=None
        # Reopen old scene15 using the updated runtime: zero-tilt compatibility.
        assert (await omni.usd.get_context().open_stage_async(str(paths[0])))[0]
        manager=SceneSession(ROOT,config=cfg,artifact_dir=OUT,show_ui=False)
        await manager.refresh();assert manager.instance,manager.error
        old=manager.instance;old.timeline.play()
        for _ in range(80):
            await advance(1,old)
            if old.camera.latest is not None:break
        check('scene15_still_renders',old.camera.latest is not None)
        check('scene15_zero_tilt',old.motion.base_controller.tilt_angles()=={'pitch':0.,'roll':0.})
        await manager.close();manager=None
        report.update(passed=True,status='complete')
    except Exception:
        report.update(passed=False,status='failed',error=traceback.format_exc())
        print(report['error'],flush=True)
    finally:
        if manager:
            try:await manager.close()
            except Exception:report.update(passed=False,cleanup_error=traceback.format_exc())
        try:await omni.usd.get_context().close_stage_async()
        except Exception:report.update(passed=False,stage_close_error=traceback.format_exc())
        report['asset_hashes_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in hashes.items())
        report['asset_sha256']=hashes
        report['passed']=report['passed'] and report['asset_hashes_unchanged']
        save();print('TILT_TERRAIN_RESULT',report['passed'],flush=True)
        app.post_quit(0 if report['passed'] else 1)


_task=asyncio.ensure_future(main())
