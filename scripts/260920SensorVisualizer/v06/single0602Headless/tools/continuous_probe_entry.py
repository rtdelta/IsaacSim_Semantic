"""Disposable native-step prototype, without the interactive owner or desktop input."""
import asyncio
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

async def main():
    import omni.kit.app
    from isaacsim.core.simulation_manager import SimulationManager, SimulationEvent
    from single0602_headless.scene import SceneStepper
    from single0602_headless.contracts import load_job, write_json
    scene = None
    callback = None
    report = {'state': 'running', 'steps': [], 'errors': []}
    path = ROOT/'reports/continuous_probe.json'
    write_json(path, report)
    try:
        job = load_job(overrides={'mode': 'interactive'})
        scene = SceneStepper(ROOT, job)
        await scene.initialize(open_scene=True, sensor_products=False)
        motion = scene.motion
        start = motion.base_controller.x
        def post(dt, context):
            try:
                motion.base_controller.x += .5*dt
                motion._apply_controlled_base(motion._command_angles())
                linear, angular = motion.articulation.get_velocities()
                dof = motion.articulation.get_dof_velocities()
                state = motion.snapshot(scene.native_time())
                report['steps'].append({'dt': dt, 'native': scene.native_time(),
                    'timeline': scene.timeline.get_current_time(), 'x': state['root_position'][0],
                    'linear': linear.numpy().tolist(), 'angular': angular.numpy().tolist(),
                    'dof': dof.numpy().tolist()})
            except Exception:
                report['errors'].append(traceback.format_exc())
        callback = SimulationManager.register_callback(post, SimulationEvent.PHYSICS_POST_STEP, order=1000)
        wall = time.monotonic()
        scene.timeline.play(); scene.timeline.commit()
        deadline = wall+15
        while len(report['steps']) < 90 and not report['errors'] and time.monotonic() < deadline:
            await scene.app.next_update_async()
        scene.timeline.pause(); scene.timeline.commit()
        report['wall_s'] = time.monotonic()-wall
        report['displacement'] = motion.snapshot(scene.native_time())['root_position'][0]-start
        report['expected'] = .5*sum(row['dt'] for row in report['steps'])
        SimulationManager.deregister_callback(callback); callback = None
        scene.timeline.stop(); scene.timeline.commit()
        await scene.app.next_update_async()
        report['ready_after_stop'] = motion.ready
        scene.timeline.play(); scene.timeline.commit()
        for _ in range(10):
            await scene.app.next_update_async()
        report['ready_after_replay'] = motion.ready
        report['tensor_valid_after_replay'] = motion.articulation.is_physics_tensor_entity_valid()
        report['state'] = 'passed' if report['steps'] and not report['errors'] else 'failed'
    except Exception:
        report.update(state='failed', error=traceback.format_exc())
    finally:
        if callback is not None:
            SimulationManager.deregister_callback(callback)
        if scene:
            await scene.close()
        write_json(path, report)
        print('S0602_CONTINUOUS_PROBE '+json.dumps({k: v for k, v in report.items() if k != 'steps'}), flush=True)
        omni.kit.app.get_app().post_quit(0 if report['state'] == 'passed' else 1)

task = asyncio.ensure_future(main())
