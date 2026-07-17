import argparse
import os
import sys
import traceback


parser = argparse.ArgumentParser(description="Minimal Isaac Sim semantic capture")
parser.add_argument(
    "--usd",
    default="/root/Desktop/wyb/Semantic_260709_01.usda",
    help="Input USD stage",
)
parser.add_argument("--camera", default="/Camera", help="USD camera prim path")
parser.add_argument(
    "--output",
    default="/root/Desktop/wyb/output_semantic_stage1",
    help="Output directory",
)
parser.add_argument("--width", type=int, default=1280)
parser.add_argument("--height", type=int, default=720)
parser.add_argument("--frames", type=int, default=1)
parser.add_argument("--warmup", type=int, default=10)
parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
args, _ = parser.parse_known_args()

from isaacsim import SimulationApp


simulation_app = SimulationApp(
    launch_config={
        "headless": args.headless,
        "renderer": "RaytracedLighting",
        "sync_loads": True,
    }
)

render_product = None
writer = None
exit_code = 0

try:
    import omni.replicator.core as rep
    import omni.usd
    from isaacsim.core.experimental.utils.stage import is_stage_loading
    from pxr import UsdGeom

    if not os.path.isfile(args.usd):
        raise FileNotFoundError(f"USD file not found: {args.usd}")
    if args.width <= 0 or args.height <= 0 or args.frames <= 0 or args.warmup < 0:
        raise ValueError("width, height and frames must be positive; warmup must be non-negative")

    print(f"[semantic-capture] Loading stage: {args.usd}")
    if not omni.usd.get_context().open_stage(args.usd):
        raise RuntimeError(f"Failed to open USD stage: {args.usd}")

    simulation_app.update()
    simulation_app.update()
    while is_stage_loading():
        simulation_app.update()

    stage = omni.usd.get_context().get_stage()
    camera_prim = stage.GetPrimAtPath(args.camera)
    if not camera_prim.IsValid() or not camera_prim.IsA(UsdGeom.Camera):
        raise RuntimeError(f"Camera prim is missing or invalid: {args.camera}")

    semantic_prim_count = sum(
        any(str(schema).startswith("SemanticsLabelsAPI") for schema in prim.GetAppliedSchemas())
        for prim in stage.Traverse()
    )
    if semantic_prim_count == 0:
        raise RuntimeError("No SemanticsLabelsAPI labels were found in the stage")

    os.makedirs(args.output, exist_ok=True)
    rep.orchestrator.set_capture_on_play(False)
    render_product = rep.create.render_product(
        args.camera,
        resolution=(args.width, args.height),
        name="SemanticCapture",
    )

    backend = rep.backends.get("DiskBackend")
    backend.initialize(output_dir=args.output)
    writer = rep.WriterRegistry.get("BasicWriter")
    writer.initialize(
        backend=backend,
        rgb=True,
        semantic_segmentation=True,
        colorize_semantic_segmentation=True,
    )
    writer.attach(render_product)

    for _ in range(args.warmup):
        simulation_app.update()

    print(
        f"[semantic-capture] Capturing {args.frames} frame(s) from {args.camera} "
        f"at {args.width}x{args.height}; semantic prims: {semantic_prim_count}"
    )
    for _ in range(args.frames):
        rep.orchestrator.step(rt_subframes=4, delta_time=0.0)

    rep.orchestrator.wait_until_complete()
    print(f"[semantic-capture] Complete: {args.output}")
except Exception as exc:
    exit_code = 1
    print(f"[semantic-capture] ERROR: {exc}", file=sys.stderr)
    traceback.print_exc()
finally:
    if writer is not None:
        writer.detach()
    if render_product is not None:
        render_product.destroy()
    simulation_app.close()

sys.exit(exit_code)
