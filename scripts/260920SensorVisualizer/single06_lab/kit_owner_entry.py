"""Owned interactive viewport for control-latency and concurrent-capture trials."""
import asyncio,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT),str(ROOT/'frozen_runtime')]
async def main():
    import omni.kit.app
    from sensor_visualizer_v06.interactive_runtime import InteractiveRuntime
    directory=Path(os.environ['SL06_OWNER_DIR']);runtime=None
    try:
        runtime=InteractiveRuntime(ROOT/'frozen_runtime',output=directory/'owner_output',socket_path=Path(os.environ['SL06_OWNER_SOCKET']))
        # Normal owner options retained. Low-rate existing hot path stats supply
        # callback timing without trace-level logging every viewport update.
        await runtime.initialize(open_scene=True)
        (directory/'kit.pid').write_text(str(os.getpid()))
        (directory/'owner_ready.json').write_text(json.dumps({'pid':os.getpid(),'sensor_products':0}))
        while not runtime.closed:await asyncio.sleep(.2)
        omni.kit.app.get_app().post_quit(0)
    except BaseException:
        traceback.print_exc()
        if runtime:
            try:await runtime.close()
            except Exception:traceback.print_exc()
        omni.kit.app.get_app().post_quit(1)
task=asyncio.ensure_future(main())
