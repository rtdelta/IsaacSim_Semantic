"""Run in Script Editor. Control server runs separately with run_web.py."""
import asyncio
from pathlib import Path
import sys
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from single0602_headless.interactive_runtime import InteractiveRuntime
if globals().get('_s0602_runtime') is not None and not _s0602_runtime.closed:
    raise RuntimeError('single0602 is already initialized. Close it before running again.')
_s0602_runtime=InteractiveRuntime(ROOT,job_path=ROOT/'config/interactive.json')
_s0602_task=asyncio.ensure_future(_s0602_runtime.initialize(open_scene=False))
def _s0602_done(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())
_s0602_task.add_done_callback(_s0602_done)
