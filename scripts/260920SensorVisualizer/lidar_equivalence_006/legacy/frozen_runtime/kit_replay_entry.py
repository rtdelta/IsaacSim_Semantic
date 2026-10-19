import asyncio
import os
from pathlib import Path
import sys
import threading
import traceback
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
async def main():
    import omni.kit.app
    code=1
    try:
        # A headless capture needs only the sensor RenderProducts.
        import omni.kit.viewport.utility as viewport_utility
        viewport=viewport_utility.get_active_viewport()
        if viewport is not None:viewport.updates_enabled=False
        from sensor_visualizer_v06.contracts import load_job
        from sensor_visualizer_v06.replay_capture import ReplayCapture
        code=await ReplayCapture(ROOT,load_job(os.environ['SV06_JOB'])).run()
    except Exception:traceback.print_exc()
    finally:
        timer=threading.Timer(15,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)
task=asyncio.ensure_future(main())
