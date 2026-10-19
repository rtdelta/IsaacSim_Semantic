"""Open scene14, then run this file in Isaac Sim Script Editor."""
import asyncio
import builtins
import importlib
from pathlib import Path
import sys

PROJECT_DIR = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
if '__file__' in globals() and Path(__file__).name == 'run_in_isaac.py':
    PROJECT_DIR = Path(__file__).resolve().parent


async def launch(previous_launch):
    if previous_launch and not previous_launch.done():
        await previous_launch
    previous = getattr(builtins, '_lidar_visualizer_session', None) or getattr(builtins, '_lidar_visualizer_instance', None)
    if previous:
        await previous.close()
    sys.path.insert(0, str(PROJECT_DIR)) if str(PROJECT_DIR) not in sys.path else None
    # Only remove this package after all its callbacks and graph nodes are closed.
    for name in list(sys.modules):
        if name == 'sensor_visualizer' or name.startswith('sensor_visualizer.'):
            del sys.modules[name]
    importlib.invalidate_caches()
    from sensor_visualizer.session import SceneSession
    manager = SceneSession(PROJECT_DIR)
    builtins._lidar_visualizer_session = manager
    await manager.refresh()


def report(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())


_task = asyncio.ensure_future(launch(getattr(builtins, '_lidar_visualizer_launch', None)))
builtins._lidar_visualizer_launch = _task
_task.add_done_callback(report)
