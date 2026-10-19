"""Open the combine stage, then run this in Script Editor. No Play needed."""
import asyncio
import builtins
from pathlib import Path
import sys

PROJECT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
if '__file__' in globals() and Path(__file__).name=='run_in_isaac.py': PROJECT=Path(__file__).resolve().parent

async def launch():
    previous=getattr(builtins,'_sensor_visualizer_v04',None)
    if previous and not previous.closed:
        previous.window.visible=True
        return
    if str(PROJECT) not in sys.path: sys.path.insert(0,str(PROJECT))
    from sensor_visualizer_v04.ui import CapturePanel
    builtins._sensor_visualizer_v04=CapturePanel(PROJECT)

def done(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())

_task=asyncio.ensure_future(launch()); _task.add_done_callback(done)
