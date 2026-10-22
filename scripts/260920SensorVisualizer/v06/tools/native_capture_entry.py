"""Bounded native profiling window includes Vulkan, CUDA and CPU, not only kernels."""
import asyncio,ctypes,json,os,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
async def main():
    import omni.kit.app,omni.kit.viewport.utility
    from sensor_visualizer_v06.contracts import load_job
    from sensor_visualizer_v06.replay_capture import ReplayCapture
    from sensor_visualizer_v06.scene import SceneStepper
    api=ctypes.CDLL('/usr/local/cuda/lib64/libnvToolsExt.so.1')
    api.nvtxRangePushA.argtypes=[ctypes.c_char_p];api.nvtxRangePop.argtypes=[]
    original=SceneStepper.capture
    async def profiled(scene,group,stamp):
        selected=group==1
        if selected:api.nvtxRangePushA(b'SV06_PROFILE')
        try:return await original(scene,group,stamp)
        finally:
            if selected:api.nvtxRangePop()
    SceneStepper.capture=profiled
    viewport=omni.kit.viewport.utility.get_active_viewport()
    if viewport:viewport.updates_enabled=False
    code=1
    try:code=await ReplayCapture(ROOT,load_job(os.environ['SV06_JOB'])).run()
    finally:
        SceneStepper.capture=original
        timer=threading.Timer(15,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)
task=asyncio.ensure_future(main())
def done(t):
    if not t.cancelled() and t.exception():
        import traceback,omni.kit.app
        traceback.print_exception(t.exception());omni.kit.app.get_app().post_quit(1)
task.add_done_callback(done)
