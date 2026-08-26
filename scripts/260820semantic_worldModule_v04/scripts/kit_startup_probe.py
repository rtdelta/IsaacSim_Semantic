"""Auto-close probe executed by Kit with --exec."""

import asyncio

import omni.kit.app
import omni.ui as ui


async def _probe() -> None:
    app = omni.kit.app.get_app()
    for _ in range(8):
        await app.next_update_async()
    manager = app.get_extension_manager()
    enabled = manager.is_extension_enabled("semantic.capture.studio")
    window = ui.Workspace.get_window("Semantic Capture Studio")
    if not enabled:
        print("V04_KIT_PROBE_FAIL extension_disabled", flush=True)
        app.post_quit(2)
        return
    if window is None:
        print("V04_KIT_PROBE_FAIL window_missing", flush=True)
        app.post_quit(3)
        return
    print(
        "V04_KIT_PROBE_OK extension_enabled=true window_exists=true",
        flush=True,
    )
    app.post_quit(0)


asyncio.ensure_future(_probe())

