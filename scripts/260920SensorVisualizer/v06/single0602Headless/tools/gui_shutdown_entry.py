"""Native GUI lifecycle smoke test; does not automate desktop input."""
import asyncio
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from single0602_headless.interactive_runtime import InteractiveRuntime

async def main():
    import omni.kit.app
    runtime=InteractiveRuntime(ROOT,job_path=ROOT/'config/interactive.json')
    await runtime.initialize(open_scene=True)
    await asyncio.sleep(.2)
    await runtime.close()
    print('S0602_GUI_CLEANUP_COMPLETE',flush=True)
    omni.kit.app.get_app().post_quit(0)

task=asyncio.ensure_future(main())
