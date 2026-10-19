"""Task-owned headless entry; never run this file in an existing GUI."""
import asyncio
import os
from pathlib import Path
import sys
import threading
import traceback
import faulthandler
faulthandler.enable(all_threads=False)

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

async def main():
    import omni.kit.app
    code=1
    try:
        from sensor_visualizer_v06.contracts import load_job
        from sensor_visualizer_v06.coordinator import CaptureRunner
        runner=CaptureRunner(ROOT,load_job(os.environ['SV06_JOB']))
        result=await runner.run()
        code=0 if result['state']=='finished' else 1
    except Exception:
        traceback.print_exc()
    finally:
        # All task files and the separate writer are closed before native shutdown.
        timer=threading.Timer(15,lambda:os._exit(code)); timer.daemon=True; timer.start()
        omni.kit.app.get_app().post_quit(code)

_sv06_task=asyncio.ensure_future(main())
