"""Owned Kit acceptance instance; separate ROS domain/output, source USD unchanged."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import traceback
import omni.kit.app
import omni.usd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/unified_bag/acceptance'
OUT.mkdir(parents=True,exist_ok=True)
SCENE=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
sys.path.insert(0,str(ROOT))


async def main():
    app=omni.kit.app.get_app();manager=None
    report=dict(passed=False,status='opening',checks={})
    original=hashlib.sha256(SCENE.read_bytes()).hexdigest()
    def save(): (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def check(name,condition):
        report['checks'][name]=bool(condition)
        if not condition:raise AssertionError(name)
    try:
        from sensor_visualizer.config import load_config
        from sensor_visualizer.session import SceneSession
        save()
        assert (await omni.usd.get_context().open_stage_async(str(SCENE)))[0]
        for _ in range(8):await app.next_update_async()
        config=load_config(ROOT/'config/sensors.json');config['ros_domain_id']=147
        config['output_directory']=str(OUT/'recordings')
        report['status']='initializing';save()
        manager=SceneSession(ROOT,config=config,artifact_dir=OUT,show_ui=True)
        await manager.refresh();r=manager.instance
        assert r is not None,manager.error
        check('camera_ids_back',set(r.camera.cameras)=={'front','back','left','right'})
        check('legacy_scene_mount_preserved',r.camera.cameras['back'].path.endswith('/FisheyeRear'))
        check('monitor_label',r.performance_label is not None)
        report['status']='warming';save();r.timeline.play()
        for _ in range(120):
            await app.next_update_async()
            assert not r.motion.failed
            assert not r.camera.error,r.camera.error
            if r.camera.latest is not None and r.motion.ready:break
        else:raise AssertionError('No camera group after warmup')
        report['status']='recording';save()
        session=await r.start_recording()
        report['session']=str(session);save()
        for _ in range(48):
            await app.next_update_async()
            assert not r.camera.error,r.camera.error
        report['status']='stopping_and_packing';save()
        await r.stop_recording()
        r.timeline.pause()
        export=json.loads((session/'unified_export_report.json').read_text())
        check('automatic_export_complete',export['state']=='complete')
        check('four_streams',set(export['image_counts'])=={'front','back','left','right'})
        check('at_least_four_groups',export['groups']>=4)
        check('pointclouds_retained',all(export['source_counts'].get(s['topic'],0)>0 for s in r.config['sensors']))
        check('back_directory', (session/'cameras/back/frames.jsonl').is_file())
        check('no_new_rear_directory',not (session/'cameras/rear').exists())
        report['export']={k:export[k] for k in ('output','groups','image_counts','elapsed_s')}
        perf=r.performance.directory;report['performance']=str(perf)
        await manager.close();manager=None
        summary=json.loads((perf/'summary.json').read_text())
        check('timings_flushed',all(k in summary['spans'] for k in ('camera.png_encode_write.back','motion.tick','pacing.wait','recording.pack_and_verify')))
        check('telemetry_healthy',summary['error'] is None and summary['dropped_telemetry_events']==0)
        check('resources_sampled',(perf/'resources.jsonl').stat().st_size>0)
        check('source_scene_unchanged',hashlib.sha256(SCENE.read_bytes()).hexdigest()==original)
        report.update(passed=True,status='complete')
    except Exception:
        report.update(status='failed',error=traceback.format_exc())
    finally:
        if manager:
            try:await manager.close()
            except Exception:report['close_error']=traceback.format_exc()
        save();app.post_quit(0 if report['passed'] else 1)


asyncio.ensure_future(main())
