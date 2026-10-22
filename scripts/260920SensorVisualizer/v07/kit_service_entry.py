"""Resident capture entry, used only by a project-owned independent Kit process."""
import asyncio
import faulthandler
import os
from pathlib import Path
import sys
import threading
faulthandler.enable(all_threads=False)
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

async def main():
    import omni.kit.app
    from sensor_visualizer_v07.contracts import load_job
    from sensor_visualizer_v07.capture_service import CaptureService
    code=1
    try:
        global service
        service=CaptureService(ROOT,load_job(os.environ['SV07_JOB']))
        await service.run();code=0
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        timer=threading.Timer(15,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)

task=asyncio.ensure_future(main())
