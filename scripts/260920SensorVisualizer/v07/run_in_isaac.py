"""Run in Script Editor. Control server runs separately with run_web.py."""
import asyncio
from pathlib import Path
import sys
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from sensor_visualizer_v07.interactive_runtime import InteractiveRuntime
if globals().get('_sv07_runtime') is not None and not _sv07_runtime.closed:
    raise RuntimeError('v07 is already initialized. Close it before running again.')
_sv07_runtime=InteractiveRuntime(ROOT,job_path=ROOT/'config/interactive.json')
_sv07_task=asyncio.ensure_future(_sv07_runtime.initialize(open_scene=False))
def _sv07_done(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())
_sv07_task.add_done_callback(_sv07_done)
