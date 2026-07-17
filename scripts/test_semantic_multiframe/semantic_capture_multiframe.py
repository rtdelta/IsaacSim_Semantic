import argparse
import json
import math
import os
import random
import shutil
import struct
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Capture paired RGB and semantic image sequences in Isaac Sim")
    parser.add_argument("--usd", default="/root/Desktop/wyb/Semantic_260709_01.usd", help="Input USD stage")
    parser.add_argument("--camera", default="/Camera", help="USD camera prim path")
    parser.add_argument(
        "--output",
        default="/root/Desktop/wyb/output_semantic_multiframe",
        help="Output directory",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--advance-mode", choices=("static", "timeline", "physics"), default="timeline")
    parser.add_argument("--capture-fps", type=float, default=10.0)
    parser.add_argument("--simulation-fps", type=float, default=60.0)
    parser.add_argument("--start-time", type=float, default=0.0)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--rt-subframes", type=int, default=4)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--frame-padding", type=int, default=4)
    parser.add_argument("--stage-timeout", type=float, default=120.0)
    parser.add_argument("--flush-interval", type=int, default=10)
    parser.add_argument("--log-interval", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--portable-root",
        default="/tmp/isaacsim_semantic_multiframe_portable",
        help="Isolated Kit portable directory, useful when another Isaac Sim process is running",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--fail-on-empty-semantic",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args, _ = parser.parse_known_args()
    return args


def validate_args(args):
    if not os.path.isfile(args.usd):
        raise FileNotFoundError(f"USD file not found: {args.usd}")

    positive_values = {
        "width": args.width,
        "height": args.height,
        "frames": args.frames,
        "capture_fps": args.capture_fps,
        "simulation_fps": args.simulation_fps,
        "rt_subframes": args.rt_subframes,
        "frame_padding": args.frame_padding,
        "stage_timeout": args.stage_timeout,
    }
    invalid = [name for name, value in positive_values.items() if value <= 0]
    if invalid:
        raise ValueError(f"These parameters must be positive: {', '.join(invalid)}")
    if args.warmup < 0 or args.start_index < 0 or args.start_time < 0:
        raise ValueError("warmup, start-index and start-time must be non-negative")
    if args.flush_interval < 0 or args.log_interval < 0:
        raise ValueError("flush-interval and log-interval must be non-negative")

    steps_per_capture = args.simulation_fps / args.capture_fps
    rounded_steps = round(steps_per_capture)
    if args.advance_mode != "static" and not math.isclose(steps_per_capture, rounded_steps, abs_tol=1e-9):
        raise ValueError("simulation-fps must be an integer multiple of capture-fps")
    return 0 if args.advance_mode == "static" else int(rounded_steps)


def prepare_output(output_dir, usd_path, overwrite):
    output_path = Path(output_dir).expanduser().resolve()
    usd_parent = Path(usd_path).expanduser().resolve().parent
    protected_paths = {Path(output_path.anchor), Path.home().resolve(), usd_parent}

    if overwrite and output_path in protected_paths:
        raise ValueError(f"Refusing to overwrite protected directory: {output_path}")
    if output_path.exists() and any(output_path.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output_path}; use --overwrite to replace it")
        shutil.rmtree(output_path)

    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def load_stage(simulation_app, omni_usd, is_stage_loading, usd_path, timeout_seconds):
    print(f"[semantic-multiframe] Loading stage: {usd_path}")
    if not omni_usd.get_context().open_stage(usd_path):
        raise RuntimeError(f"Failed to open USD stage: {usd_path}")

    simulation_app.update()
    simulation_app.update()
    deadline = time.monotonic() + timeout_seconds
    while is_stage_loading():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Stage loading exceeded {timeout_seconds:.1f} seconds")
        simulation_app.update()

    stage = omni_usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("USD context returned no stage after loading")
    return stage


def validate_stage(stage, camera_path, usd_geom):
    camera_prim = stage.GetPrimAtPath(camera_path)
    if not camera_prim.IsValid() or not camera_prim.IsA(usd_geom.Camera):
        raise RuntimeError(f"Camera prim is missing or invalid: {camera_path}")

    semantic_prim_count = sum(
        any(str(schema).startswith("SemanticsLabelsAPI") for schema in prim.GetAppliedSchemas())
        for prim in stage.Traverse()
    )
    if semantic_prim_count == 0:
        raise RuntimeError("No SemanticsLabelsAPI labels were found in the stage")
    return semantic_prim_count


def read_png_size(path):
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Invalid PNG file: {path}")
    return struct.unpack(">II", header[16:24])


def validate_outputs(output_path, args, frame_times):
    frame_records = []
    for offset, capture_time in enumerate(frame_times):
        frame_index = args.start_index + offset
        frame_token = f"{frame_index:0{args.frame_padding}d}"
        rgb_name = f"rgb_{frame_token}.png"
        semantic_name = f"semantic_segmentation_{frame_token}.png"
        labels_name = f"semantic_segmentation_labels_{frame_token}.json"
        rgb_path = output_path / rgb_name
        semantic_path = output_path / semantic_name
        labels_path = output_path / labels_name

        missing = [str(path) for path in (rgb_path, semantic_path, labels_path) if not path.is_file()]
        if missing:
            raise RuntimeError(f"Missing output files for frame {frame_index}: {missing}")

        rgb_size = read_png_size(rgb_path)
        semantic_size = read_png_size(semantic_path)
        expected_size = (args.width, args.height)
        if rgb_size != expected_size or semantic_size != expected_size:
            raise RuntimeError(
                f"Unexpected image size at frame {frame_index}: RGB={rgb_size}, semantic={semantic_size}, "
                f"expected={expected_size}"
            )

        with labels_path.open("r", encoding="utf-8") as stream:
            labels = json.load(stream)
        semantic_classes = sorted(
            {
                str(value.get("class"))
                for value in labels.values()
                if isinstance(value, dict) and value.get("class") not in (None, "BACKGROUND", "UNLABELLED")
            }
        )
        if args.fail_on_empty_semantic and not semantic_classes:
            raise RuntimeError(f"No foreground semantic classes were written for frame {frame_index}")

        frame_records.append(
            {
                "frame_index": frame_index,
                "capture_time_seconds": round(capture_time, 9),
                "rgb": rgb_name,
                "semantic_segmentation": semantic_name,
                "semantic_labels": labels_name,
                "semantic_classes": semantic_classes,
            }
        )
    return frame_records


def write_manifest(output_path, args, semantic_prim_count, steps_per_capture, isaac_version, frame_records):
    manifest = {
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "isaac_sim_version": isaac_version,
        "usd": str(Path(args.usd).resolve()),
        "camera": args.camera,
        "output": str(output_path),
        "resolution": {"width": args.width, "height": args.height},
        "advance_mode": args.advance_mode,
        "frame_count": args.frames,
        "start_index": args.start_index,
        "capture_fps": args.capture_fps,
        "simulation_fps": args.simulation_fps,
        "simulation_steps_per_capture": steps_per_capture,
        "start_time_seconds": args.start_time,
        "warmup_frames": args.warmup,
        "rt_subframes": args.rt_subframes,
        "seed": args.seed,
        "portable_root": args.portable_root,
        "semantic_prim_count": semantic_prim_count,
        "frames": frame_records,
    }
    manifest_path = output_path / "sequence_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest_path


args = parse_args()

# Avoid sharing Kit's portable data with an already-running Isaac Sim GUI.
if "--portable-root" not in sys.argv:
    sys.argv.extend(["--portable-root", args.portable_root])

from isaacsim import SimulationApp


simulation_app = SimulationApp(
    launch_config={
        "headless": args.headless,
        "renderer": "RaytracedLighting",
        "sync_loads": True,
        "width": args.width,
        "height": args.height,
    }
)

render_product = None
writer = None
timeline = None
exit_code = 0

try:
    import carb.settings
    import omni.replicator.core as rep
    import omni.timeline
    import omni.usd
    from isaacsim.core.experimental.utils.stage import is_stage_loading
    from isaacsim.core.simulation_manager import SimulationManager
    from isaacsim.core.version import get_version
    from pxr import UsdGeom

    steps_per_capture = validate_args(args)
    output_path = prepare_output(args.output, args.usd, args.overwrite)
    random.seed(args.seed)
    rep.set_global_seed(args.seed)
    rep.orchestrator.set_capture_on_play(False)

    stage = load_stage(simulation_app, omni.usd, is_stage_loading, args.usd, args.stage_timeout)
    semantic_prim_count = validate_stage(stage, args.camera, UsdGeom)

    timeline = omni.timeline.get_timeline_interface()
    timeline.set_looping(False)
    timeline.set_current_time(args.start_time)
    timeline.set_end_time(args.start_time + max(1.0, args.frames / args.capture_fps + 1.0))
    timeline.set_time_codes_per_second(args.simulation_fps)
    timeline.commit()

    if args.advance_mode == "timeline":
        carb.settings.get_settings().set("/app/player/useFixedTimeStepping", True)
    elif args.advance_mode == "physics":
        SimulationManager.set_physics_dt(1.0 / args.simulation_fps)
        SimulationManager.initialize_physics()

    render_product = rep.create.render_product(
        args.camera,
        resolution=(args.width, args.height),
        name="SemanticMultiframeCapture",
    )
    backend = rep.backends.get("DiskBackend")
    backend.initialize(output_dir=str(output_path))
    writer = rep.WriterRegistry.get("BasicWriter")
    writer.initialize(
        backend=backend,
        rgb=True,
        semantic_segmentation=True,
        colorize_semantic_segmentation=True,
        frame_padding=args.frame_padding,
    )
    if args.start_index:
        if not hasattr(writer, "_frame_id"):
            raise RuntimeError("Installed BasicWriter does not support setting a start index")
        writer._frame_id = args.start_index
    writer.attach(render_product)

    for _ in range(args.warmup):
        simulation_app.update()
    render_product.hydra_texture.set_updates_enabled(False)

    print(
        f"[semantic-multiframe] Capturing {args.frames} paired frame(s), mode={args.advance_mode}, "
        f"camera={args.camera}, resolution={args.width}x{args.height}, semantic_prims={semantic_prim_count}"
    )
    frame_times = []
    for frame_offset in range(args.frames):
        if args.advance_mode == "timeline":
            target_time = args.start_time + frame_offset / args.capture_fps
            timeline.pause()
            timeline.set_current_time(target_time)
            timeline.commit()
            simulation_app.update()
            capture_time = timeline.get_current_time()
            if not math.isclose(capture_time, target_time, abs_tol=1e-6):
                raise RuntimeError(
                    f"Timeline did not reach target time: target={target_time}, actual={capture_time}"
                )
        elif args.advance_mode == "physics":
            if frame_offset > 0:
                SimulationManager.step(steps=steps_per_capture)
            capture_time = args.start_time + frame_offset / args.capture_fps
        else:
            capture_time = args.start_time

        render_product.hydra_texture.set_updates_enabled(True)
        rep.orchestrator.step(delta_time=0.0, pause_timeline=True, rt_subframes=args.rt_subframes)
        render_product.hydra_texture.set_updates_enabled(False)
        frame_times.append(capture_time)

        completed = frame_offset + 1
        if args.flush_interval and completed % args.flush_interval == 0:
            rep.orchestrator.wait_until_complete()
        if args.log_interval and (completed % args.log_interval == 0 or completed == args.frames):
            print(f"[semantic-multiframe] Captured {completed}/{args.frames} frame(s)")

    rep.orchestrator.wait_until_complete()
    if timeline.is_playing():
        timeline.pause()

    frame_records = validate_outputs(output_path, args, frame_times)
    version_info = get_version()
    isaac_version = version_info[0] if version_info else ""
    manifest_path = write_manifest(
        output_path,
        args,
        semantic_prim_count,
        steps_per_capture,
        isaac_version,
        frame_records,
    )
    print(f"[semantic-multiframe] Complete: {output_path}")
    print(f"[semantic-multiframe] Manifest: {manifest_path}")
except Exception as exc:
    exit_code = 1
    print(f"[semantic-multiframe] ERROR: {exc}", file=sys.stderr)
    traceback.print_exc()
finally:
    if timeline is not None and timeline.is_playing():
        timeline.pause()
    if writer is not None:
        writer.detach()
    if render_product is not None:
        render_product.destroy()
    simulation_app.close()

sys.exit(exit_code)
