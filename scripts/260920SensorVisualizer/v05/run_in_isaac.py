"""Run in Script Editor. Control server runs separately with run_web.py."""
import asyncio
from pathlib import Path
import sys
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from sensor_visualizer_v05.interactive_runtime import InteractiveRuntime
if globals().get('_sv05_runtime') is not None and not _sv05_runtime.closed:
    raise RuntimeError('v05 is already initialized. Close it before running again.')
_sv05_runtime=InteractiveRuntime(ROOT)
_sv05_task=asyncio.ensure_future(_sv05_runtime.initialize(open_scene=False))
def _sv05_done(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())
_sv05_task.add_done_callback(_sv05_done)
