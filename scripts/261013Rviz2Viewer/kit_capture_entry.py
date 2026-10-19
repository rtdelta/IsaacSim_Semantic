"""Task-owned Isaac entry. The copied single06 acquisition code stays unchanged."""
import asyncio, json, os, sys, threading, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'capture_runtime/frozen_runtime'),str(ROOT)]

async def main():
    import omni.kit.app,omni.kit.viewport.utility
    from sensor_visualizer_v06.contracts import load_job
    from sensor_visualizer_v06.replay_capture import ReplayCapture
    from capture_observer import install
    out=Path(os.environ['SL06_SPEC']).parent
    install(out)
    Path(os.environ['SL06_PID_FILE']).write_text(str(os.getpid()))
    viewport=omni.kit.viewport.utility.get_active_viewport()
    if viewport:viewport.updates_enabled=False
    code=1
    try:
        capture=ReplayCapture(ROOT/'capture_runtime/frozen_runtime',load_job(os.environ['SV06_JOB']))
        code=await capture.run()
        (out/'sessions.json').write_text(json.dumps([str(capture.session)]))
    except BaseException:traceback.print_exc()
    finally:
        timer=threading.Timer(20,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)

task=asyncio.ensure_future(main())
