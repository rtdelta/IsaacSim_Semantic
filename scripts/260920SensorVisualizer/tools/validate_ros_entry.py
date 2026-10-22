"""Full Kit experience: check runtime startup, failure guard and ROS transport.

Run via the publisher launch_isaac.py --/app/settings/persistent=false --exec <this file>.
Keep the GUI enabled: this installed Full experience faults in its line shader
with --no-window/--app/window/hideUi during point-cloud attachment.
Uses a private ROS domain and artifact directory; never edits production config.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import omni.kit.app
import omni.usd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'reports/ros_entry'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT/'result.json'
REPORT.write_text(json.dumps({'passed': False, 'status': 'starting'}))
PROJECT = Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer')
sys.path.insert(0, str(PROJECT))


async def main():
    app = omni.kit.app.get_app()
    manager = observer = observer_log = None
    report = {'passed': False, 'ros_domain_id': 137}
    try:
        from lidar_visualizer.config import load_config
        from lidar_visualizer.session import SceneSession
        from lidar_visualizer.runtime import LidarVisualizer
        from lidar_visualizer.state_publication import StatePublication
        from lidar_visualizer.cloud_rate import CloudPublishers
        from lidar_visualizer.recording import ros_command, ros_environment
        config = load_config(PROJECT/'config/sensors.json')
        config['ros_domain_id'] = report['ros_domain_id']
        config['output_directory'] = str(OUT/'unused_recording_output')
        config['control_mode'] = os.environ.get('SV_ROS_TEST_MODE', 'scripted')
        if os.environ.get('SV_ROS_TEST_SMALL_PRODUCTS') or os.environ.get('SV_ROS_TEST_GMO_ONLY'):
            import omni.replicator.core as rep
            original_product = rep.create.render_product
            def small_product(camera, resolution, **kwargs):
                if os.environ.get('SV_ROS_TEST_GMO_ONLY'):
                    kwargs['render_vars'] = ['GenericModelOutput']
                return original_product(camera, (1, 1) if os.environ.get('SV_ROS_TEST_SMALL_PRODUCTS') else resolution, **kwargs)
            rep.create.render_product = small_product
        # Test-only stage markers; production behavior remains unchanged.
        for cls, name in ((LidarVisualizer, '_create_publishers'),
                          (StatePublication, 'build'), (CloudPublishers, 'attach')):
            original = getattr(cls, name)
            async def traced(self, *args, _original=original, _label=cls.__name__+'.'+name, **kwargs):
                print('ROS_ENTRY_BEGIN', _label, flush=True)
                if _label == 'LidarVisualizer._create_publishers' and os.environ.get('SV_ROS_TEST_DRAIN'):
                    for _ in range(12): await app.next_update_async()
                    print('ROS_ENTRY_DRAINED', flush=True)
                result = await _original(self, *args, **kwargs)
                print('ROS_ENTRY_END', _label, flush=True)
                return result
            setattr(cls, name, traced)
        scene = '/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_13_3dgs_contract.usda'
        result = await omni.usd.get_context().open_stage_async(scene)
        assert result[0], result
        for _ in range(12): await app.next_update_async()
        print('ROS_ENTRY_STAGE_OPEN', flush=True)
        # An invalid launch must be rejected before any native ROS bridge call.
        original_library_path = os.environ.get('LD_LIBRARY_PATH')
        try:
            os.environ['LD_LIBRARY_PATH'] = ''
            rejected = LidarVisualizer(PROJECT, config, artifact_dir=OUT)
            try:
                await rejected.initialize(show_ui=False)
                raise AssertionError('Missing ROS launch environment was not rejected')
            except RuntimeError as exc:
                assert 'ROS launch environment is incomplete' in str(exc), str(exc)
                report['bad_environment_guard_passed'] = True
        finally:
            if original_library_path is None: os.environ.pop('LD_LIBRARY_PATH', None)
            else: os.environ['LD_LIBRARY_PATH'] = original_library_path
        manager = SceneSession(PROJECT, config=config, artifact_dir=OUT, show_ui=False)
        await manager.refresh()
        assert manager.instance is not None, manager.error
        instance = manager.instance
        sensors = instance.config['sensors']
        assert len(sensors) == 13
        report['scripted_initialized'] = True
        print('ROS_ENTRY_INITIALIZED', len(sensors), flush=True)
        observer_log = (OUT/'observer.log').open('wb')
        observer = subprocess.Popen(ros_command(instance.config, [
            '/usr/bin/python3', str(PROJECT/'validation/observe_ros.py'),
            '--output', str(OUT/'received.json'), '--seconds', '70', '--topics',
            *[s['topic'] for s in sensors]]), env=ros_environment(instance.config),
            stdout=observer_log, stderr=subprocess.STDOUT, start_new_session=True)
        instance.timeline.play()
        deadline = time.monotonic() + 55
        received = {}
        while time.monotonic() < deadline:
            await app.next_update_async()
            assert observer.poll() is None, 'ROS observer exited early'
            try: received = json.loads((OUT/'received.json').read_text())
            except (FileNotFoundError, json.JSONDecodeError): continue
            if (all(received['clouds'].get(s['topic'], {}).get('messages', 0) >= 2 and
                    received['clouds'][s['topic']]['max_points'] > 0 for s in sensors) and
                received.get('clock_count', 0) > 0 and
                all(s['frame_id'] in received.get('tf', {}) for s in sensors)):
                break
        else: raise AssertionError('Missing ROS clouds, TF or clock: '+json.dumps(received))
        assert instance.motion.ready and instance.state_publication.count > 0
        report['scripted_state_messages'] = instance.state_publication.count
        report['ros_received'] = received
        print('ROS_ENTRY_TRANSPORT_OK', flush=True)
        instance.timeline.stop()
        await manager.refresh(mode='observe')
        assert manager.instance is not None, manager.error
        instance = manager.instance
        instance.timeline.play()
        for _ in range(25): await app.next_update_async()
        assert instance.motion.ready and instance.motion.mode == 'observe'
        assert instance.state_publication.count > 0
        report['observe_initialized'] = True
        report['observe_state_messages'] = instance.state_publication.count
        instance.timeline.stop()
        report.update(passed=True, status='complete')
    except Exception:
        report.update(passed=False, status='failed', error=traceback.format_exc())
        print(report['error'], flush=True)
    finally:
        if observer and observer.poll() is None:
            observer.send_signal(signal.SIGINT)
            deadline = time.monotonic()+5
            while observer.poll() is None and time.monotonic()<deadline:
                await app.next_update_async()
            if observer.poll() is None: observer.terminate()
        if observer_log: observer_log.close()
        if manager:
            try: await manager.close()
            except Exception: report.update(passed=False, cleanup_error=traceback.format_exc())
        # Direct context close discards this test's unsaved stage state and avoids
        # the GUI's Save / Don't Save dialog when post_quit is issued below.
        try: await omni.usd.get_context().close_stage_async()
        except Exception: report.update(passed=False, stage_close_error=traceback.format_exc())
        REPORT.write_text(json.dumps(report, indent=2)+'\n')
        print('ROS_ENTRY_RESULT', report['passed'], flush=True)
        app.post_quit(0 if report['passed'] else 1)


_validation_task = asyncio.ensure_future(main())
