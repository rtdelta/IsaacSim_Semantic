"""Run inside native Kit. Reuse production publishing and recording code."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
import traceback
import numpy as np
import omni.kit.app
import omni.usd
from pxr import Usd, UsdGeom

JOB = json.loads(Path(os.environ['AIRY_CAPTURE_REQUEST']).read_text())
OUT = Path(JOB['job_dir'])
PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT/'tools'), JOB['visualizer']]
from prepare_stage import prepare, verify, sha
from lidar_visualizer.config import load_config
from lidar_visualizer.runtime import LidarVisualizer

REPORT = dict(passed=False, request=JOB)


def progress(phase, **extra):
    data = dict(phase=phase, **extra)
    (OUT/'progress.json').write_text(json.dumps(data, indent=2)+'\n')
    print('AIRY_CAPTURE', json.dumps(data), flush=True)


async def main():
    runtime = None
    app = omni.kit.app.get_app()
    async def frames(n):
        for _ in range(n): await app.next_update_async()
    try:
        progress('preparing_stage')
        if JOB['reuse_stage']:
            conversion = json.loads((PROJECT/'reports/stage12_conversion.json').read_text())
            assert conversion['scene'] == JOB['stage'] and sha(JOB['stage']) == conversion['scene_sha256']
        else:
            conversion = prepare(JOB['source'], JOB['stage'], JOB['asset'], PROJECT/'reports/stage12_conversion.json')
        REPORT['conversion'] = conversion
        progress('opening_scene')
        ctx = omni.usd.get_context()
        opened = await ctx.open_stage_async(JOB['stage'])
        assert opened[0], opened
        while ctx.get_stage_loading_status()[2]: await frames(1)
        stage = ctx.get_stage()
        REPORT['mount_verification'] = verify(stage, conversion)
        cfg = load_config(Path(JOB['visualizer'])/'config/sensors.json')
        cfg['ros_domain_id'] = JOB['domain']
        cfg['control_mode'] = 'scripted'
        cfg['robot_motion']['forward_speed_m_s'] = 0
        cfg['output_directory'] = str(OUT/'captures')
        progress('connecting_publishers')
        runtime = LidarVisualizer(JOB['visualizer'], cfg, artifact_dir=OUT/'runtime')
        await runtime.initialize(show_ui=False)
        assert len(runtime.config['sensors']) == 13
        progress('warming_up')
        runtime.timeline.play()
        start = time.monotonic()
        while not (runtime.motion.ready and all(g.published >= 3 for g in runtime.cloud_publishers.stats.values())):
            assert not runtime.motion.failed, runtime.status
            assert time.monotonic()-start < 180, 'Timed out waiting for nonempty clouds from all sensors'
            await frames(1)
        runtime.motion.command('hold')
        initial = deepcopy(runtime.motion.last_snapshot)
        REPORT['initial_state'] = initial
        REPORT['sensor_world_matrices'] = {s['frame_id']: np.asarray(UsdGeom.Xformable(
            stage.GetPrimAtPath(s['prim_path'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T.tolist()
            for s in runtime.config['sensors']}
        ids = [s['id'] for s in runtime.config['sensors']]
        session = await runtime.start_recording(sensor_ids=ids, output_directory=str(OUT/'captures'))
        REPORT['session'] = str(session)
        (OUT/'session_path.txt').write_text(str(session)+'\n')
        # Wait for rosbag's actual subscriptions before the timed capture interval.
        start = time.monotonic()
        while True:
            log = (session/'recorder.log').read_text(errors='replace')
            if all("Subscribed to topic '"+s['topic']+"'" in log for s in runtime.config['sensors']): break
            assert runtime.recorder.running, 'Recorder exited during discovery'
            assert time.monotonic()-start < 45, 'Recorder topic discovery timed out'
            await frames(1)
        sim_start = runtime.timeline.get_current_time(); wall_start = time.monotonic()
        progress('recording', session=str(session), simulation_start=sim_start, seconds=JOB['seconds'])
        while runtime.timeline.get_current_time()-sim_start < JOB['seconds']-1e-8:
            await frames(1)
            assert runtime.recorder.running and not runtime.motion.failed, runtime.status
            assert time.monotonic()-wall_start < 240, 'Capture progress timed out'
        sim_end = runtime.timeline.get_current_time(); wall_duration = time.monotonic()-wall_start
        REPORT['final_state'] = deepcopy(runtime.motion.last_snapshot)
        REPORT['capture_interval'] = dict(simulation_start=sim_start, simulation_end=sim_end,
            simulation_seconds=sim_end-sim_start, wall_seconds=wall_duration,
            real_time_factor=(sim_end-sim_start)/wall_duration)
        REPORT['gates'] = {sid:dict(published=g.published, throttled=g.throttled, empty=g.empty)
                           for sid,g in runtime.cloud_publishers.stats.items()}
        REPORT['render_lease'] = runtime.render_lease.metadata()
        await runtime.stop_recording()
        runtime.timeline.pause()
        for field in ('positions','root_position','root_xyzw'):
            np.testing.assert_allclose(REPORT['final_state'][field], initial[field], atol=2e-5)
        assert (session/'bag/metadata.yaml').is_file()
        REPORT['bag_bytes'] = sum(p.stat().st_size for p in (session/'bag').glob('*.mcap'))
        assert REPORT['bag_bytes'] > 100000
        assert sha(JOB['source']) == conversion['source_sha256']
        assert sha(JOB['stage']) == conversion['scene_sha256']
        REPORT['passed'] = True
        progress('recording_finished', bytes=REPORT['bag_bytes'])
    except Exception:
        REPORT['error'] = traceback.format_exc()
        print(REPORT['error'], flush=True)
    finally:
        if runtime:
            try: await runtime.close()
            except Exception:
                REPORT.update(passed=False, cleanup_error=traceback.format_exc())
        (OUT/'capture_result.json').write_text(json.dumps(REPORT, indent=2)+'\n')
        progress('complete', passed=REPORT['passed'], error=REPORT.get('error'))
        app.post_quit(0 if REPORT['passed'] else 1)


asyncio.ensure_future(main())
