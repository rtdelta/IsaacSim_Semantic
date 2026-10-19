"""Standalone interactive entry, also usable headlessly for owner tests."""
import asyncio
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from sensor_visualizer_v07.interactive_runtime import InteractiveRuntime
async def main():
    import omni.kit.app
    global runtime
    runtime=InteractiveRuntime(ROOT,socket_path=os.environ.get('SV07_SOCKET'),job_path=os.environ.get('SV07_JOB'))
    await runtime.initialize(open_scene=True)
    print('[SV07 INTERACTIVE READY]',flush=True)
    if os.environ.get('SV07_NATIVE_EVENT_TEST')=='1':
        from tools.native_event_probe import run
        await run(runtime)
    if os.environ.get('SV07_OWNER_TEST'):
        import time
        end=time.monotonic()+float(os.environ.get('SV07_OWNER_TEST'))
        while not runtime.closed and time.monotonic()<end:await asyncio.sleep(.1)
        await runtime.close();omni.kit.app.get_app().post_quit(0)
task=asyncio.ensure_future(main())
def done(t):
    if not t.cancelled() and t.exception():
        import traceback,omni.kit.app
        traceback.print_exception(t.exception());omni.kit.app.get_app().post_quit(1)
task.add_done_callback(done)
