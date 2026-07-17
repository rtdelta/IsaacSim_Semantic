"""Capture RGB, stable semantic NPY, and custom-color semantic PNG in Isaac Sim."""

import argparse
import os
import sys
import traceback
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description="Isaac Sim custom semantic capture")
parser.add_argument(
    "--usd",
    default="/root/gpufree-data/wyb/Semantic_260709_01.usd",
    help="Input USD stage",
)
parser.add_argument("--mapping", default=str(SCRIPT_DIR / "semantic_mapping.json"))
parser.add_argument("--camera", default="/Camera", help="USD camera prim path")
parser.add_argument(
    "--output",
    default="/root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01/output",
    help="Output directory; the data disk is recommended on this host",
)
parser.add_argument("--width", type=int, default=1280)
parser.add_argument("--height", type=int, default=720)
parser.add_argument("--frames", type=int, default=1)
parser.add_argument("--warmup", type=int, default=10)
parser.add_argument("--rt-subframes", type=int, default=4)
parser.add_argument(
    "--delta-time",
    type=float,
    default=0.0,
    help="Timeline time in seconds advanced by each captured frame",
)
parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--save-runtime-ids", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--strict-mapping", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--overwrite", action="store_true", help="Allow files in an existing output directory")
args, kit_args = parser.parse_known_args()
sys.argv = [sys.argv[0], *kit_args]

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
    import carb.settings
    import omni.replicator.core as rep
    import omni.usd
    from isaacsim.core.experimental.utils.stage import is_stage_loading
    from omni.replicator.core.backends import DiskBackend
    from pxr import UsdGeom

    from semantic_dataset_writer import SemanticDatasetWriter

    if not os.path.isfile(args.usd):
        raise FileNotFoundError(f"USD file not found: {args.usd}")
    if not os.path.isfile(args.mapping):
        raise FileNotFoundError(f"Semantic mapping file not found: {args.mapping}")
    if args.width <= 0 or args.height <= 0 or args.frames <= 0:
        raise ValueError("width, height, and frames must be positive")
    if args.warmup < 0 or args.rt_subframes <= 0 or args.delta_time < 0:
        raise ValueError(
            "warmup and delta-time must be non-negative; rt-subframes must be positive"
        )

    output_path = Path(args.output).resolve()
    if output_path.exists() and any(output_path.iterdir()) and not args.overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {output_path}. Use --overwrite or choose a new path."
        )

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

    carb.settings.get_settings().set("rtx/post/dlss/execMode", 2)
    rep.orchestrator.set_capture_on_play(False)
    render_product = rep.create.render_product(
        args.camera,
        resolution=(args.width, args.height),
        name="SemanticCapture",
    )

    backend = DiskBackend(output_dir=str(output_path), overwrite=True)
    writer = SemanticDatasetWriter(
        backend=backend,
        semantic_schema=args.mapping,
        rgb=True,
        save_runtime_ids=args.save_runtime_ids,
        strict_mapping=args.strict_mapping,
    )
    writer.attach(render_product)

    for _ in range(args.warmup):
        simulation_app.update()

    print(
        f"[semantic-capture] Capturing {args.frames} frame(s) from {args.camera} "
        f"at {args.width}x{args.height}; semantic prims: {semantic_prim_count}"
    )
    for _ in range(args.frames):
        rep.orchestrator.step(
            rt_subframes=args.rt_subframes,
            delta_time=args.delta_time,
        )

    rep.orchestrator.wait_until_complete()
    print(f"[semantic-capture] Complete: {backend.output_dir}")
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
