"""Run in Script Editor. Control server runs separately with run_web.py."""
import asyncio
from pathlib import Path
import sys
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from sensor_visualizer_v06.interactive_runtime import InteractiveRuntime
if globals().get('_sv06_runtime') is not None and not _sv06_runtime.closed:
    raise RuntimeError('v06 is already initialized. Close it before running again.')
_sv06_runtime=InteractiveRuntime(ROOT,job_path=ROOT/'config/interactive.json')
_sv06_task=asyncio.ensure_future(_sv06_runtime.initialize(open_scene=False))
def _sv06_done(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())
_sv06_task.add_done_callback(_sv06_done)
