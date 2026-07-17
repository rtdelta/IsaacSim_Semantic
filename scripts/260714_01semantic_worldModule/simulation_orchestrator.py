"""Top-level scheduler for the moving-excavator semantic capture pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_STAGE = PROJECT_DIR / "configs" / "usd_ply_combined_02_capture_overlay.usda"
DEFAULT_MAPPING = PROJECT_DIR / "configs" / "semantic_mapping_usd_ply_combined_02.json"
DEFAULT_TRAJECTORY = PROJECT_DIR / "trajectories" / "excavator_motion_01.csv"
DEFAULT_OUTPUT = PROJECT_DIR / "output" / "usd_ply_combined_02_motion_60hz_10fps_50f_20260714"


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Schedule world physics, excavator motion, and semantic-camera capture"
    )
    parser.add_argument("--usd", default=str(DEFAULT_STAGE), help="USD or USDA stage to open")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING), help="Stable semantic mapping JSON")
    parser.add_argument(
        "--camera",
        default="/root/Xform/operator_cab_mesh/Camera_01",
        help="Camera prim path; use an empty string to discover the only Camera below --cab-root",
    )
    parser.add_argument("--cab-root", default="/root/Xform/operator_cab_mesh")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--rt-subframes", type=int, default=4)
    parser.add_argument("--physics-hz", type=int, default=60)
    parser.add_argument("--capture-fps", type=int, default=10)
    parser.add_argument(
        "--trajectory",
        default=str(DEFAULT_TRAJECTORY),
        help="CSV keyframes with columns: time,cab,boom,small_arm,bucket",
    )
    parser.add_argument(
        "--trajectory-mode",
        choices=("loop", "hold"),
        default="loop",
        help="Loop the CSV or hold its final keyframe after the trajectory ends",
    )
    parser.add_argument(
        "--interpolation",
        choices=("linear",),
        default="linear",
    )
    parser.add_argument(
        "--enable-motion",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--save-runtime-ids",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--strict-mapping",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow writing into a non-empty output directory",
    )
    return parser.parse_known_args()


def validate_args(args: argparse.Namespace) -> None:
    if not os.path.isfile(args.usd):
        raise FileNotFoundError(f"USD file not found: {args.usd}")
    if not os.path.isfile(args.mapping):
        raise FileNotFoundError(f"Semantic mapping file not found: {args.mapping}")
    if args.frames <= 0 or args.width <= 0 or args.height <= 0:
        raise ValueError("frames, width, and height must be positive")
    if args.physics_hz <= 0 or args.capture_fps <= 0:
        raise ValueError("physics-hz and capture-fps must be positive")
    if args.physics_hz % args.capture_fps != 0:
        raise ValueError("First-version scheduling requires physics-hz to be divisible by capture-fps")
    if args.enable_motion and not os.path.isfile(args.trajectory):
        raise FileNotFoundError(f"Trajectory CSV not found: {args.trajectory}")
    if args.warmup < 0 or args.rt_subframes <= 0:
        raise ValueError("warmup must be non-negative and rt-subframes must be positive")


def ensure_output_path(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {path}. Choose a new path or pass --overwrite."
        )
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main() -> int:
    args, kit_args = parse_args()
    sys.argv = [sys.argv[0], *kit_args]

    from isaacsim import SimulationApp

    simulation_app = SimulationApp(
        launch_config={
            "headless": args.headless,
            "renderer": "RaytracedLighting",
            "sync_loads": True,
        }
    )

    camera_scheduler = None
    world_scheduler = None
    exit_code = 0

    try:
        import omni.usd
        from isaacsim.core.experimental.utils.stage import is_stage_loading

        # These modules import Kit/Replicator APIs, so load them only after SimulationApp.
        from excavator_joint_motion import ExcavatorJointMotion
        from semantic_capture_custom import SemanticCameraScheduler
        from world_scheduler import WorldScheduler

        validate_args(args)
        output_path = Path(args.output).resolve()
        ensure_output_path(output_path, args.overwrite)

        print(f"[simulation-orchestrator] Loading stage: {args.usd}")
        if not omni.usd.get_context().open_stage(args.usd):
            raise RuntimeError(f"Failed to open USD stage: {args.usd}")
        simulation_app.update()
        simulation_app.update()
        while is_stage_loading():
            simulation_app.update()

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("USD context did not return an opened stage")
        simulation_app.reset_render_settings()

        run_duration = args.frames / float(args.capture_fps)
        world_scheduler = WorldScheduler(
            simulation_app=simulation_app,
            stage=stage,
            physics_hz=args.physics_hz,
            maximum_duration_seconds=run_duration + 1.0,
        )
        world_scheduler.initialize()

        motion_scheduler = None
        if args.enable_motion:
            motion_scheduler = ExcavatorJointMotion(
                stage=stage,
                trajectory_path=Path(args.trajectory).resolve(),
                playback_mode=args.trajectory_mode,
                interpolation=args.interpolation,
                safety_margin_degrees=2.0,
            )
            motion_scheduler.initialize()

        camera_scheduler = SemanticCameraScheduler(
            simulation_app=simulation_app,
            stage=stage,
            camera_path=args.camera or None,
            cab_root=args.cab_root,
            output_path=output_path,
            mapping_path=Path(args.mapping).resolve(),
            width=args.width,
            height=args.height,
            rt_subframes=args.rt_subframes,
            save_runtime_ids=args.save_runtime_ids,
            strict_mapping=args.strict_mapping,
        )
        camera_scheduler.initialize()
        camera_scheduler.warmup(args.warmup)

        steps_per_capture = args.physics_hz // args.capture_fps
        run_config = {
            "source_stage": str(Path(args.usd).resolve()),
            "semantic_mapping": str(Path(args.mapping).resolve()),
            "camera": camera_scheduler.camera_path,
            "cab_root": args.cab_root,
            "output": str(output_path),
            "frames": args.frames,
            "resolution": [args.width, args.height],
            "physics_hz": args.physics_hz,
            "capture_fps": args.capture_fps,
            "physics_steps_per_capture": steps_per_capture,
            "motion_enabled": bool(args.enable_motion),
            "rt_subframes": args.rt_subframes,
            "warmup_updates": args.warmup,
        }
        if motion_scheduler is not None:
            run_config["trajectory"] = motion_scheduler.trajectory_info()
            run_config["joints"] = motion_scheduler.describe()
        write_json(output_path / "run_config.json", run_config)

        print(
            f"[simulation-orchestrator] Running {args.frames} capture(s), "
            f"physics={args.physics_hz} Hz, camera={args.capture_fps} FPS, "
            f"steps/capture={steps_per_capture}"
        )

        motion_state_path = output_path / "motion_state.jsonl"
        with motion_state_path.open("w", encoding="utf-8") as motion_stream:
            world_scheduler.start()
            for frame_id in range(args.frames):
                for _ in range(steps_per_capture):
                    next_time = world_scheduler.next_simulation_time
                    world_scheduler.update(next_time)
                    if motion_scheduler is not None:
                        motion_scheduler.update(next_time)
                    world_scheduler.step()

                capture_time = world_scheduler.simulation_time
                camera_scheduler.capture(frame_id=frame_id, simulation_time=capture_time)
                state = {
                    "frame_id": frame_id,
                    "simulation_time": capture_time,
                    "world": world_scheduler.get_state(),
                    "camera": camera_scheduler.get_state(),
                    "motion": motion_scheduler.get_state(capture_time)
                    if motion_scheduler is not None
                    else {"enabled": False},
                }
                motion_stream.write(json.dumps(state, ensure_ascii=False) + "\n")
                motion_stream.flush()
                print(
                    f"[simulation-orchestrator] Captured frame {frame_id + 1}/{args.frames} "
                    f"at t={capture_time:.6f}s"
                )

        camera_scheduler.wait_until_complete()
        print(f"[semantic-capture] Complete: {output_path}")
    except Exception as exc:
        exit_code = 1
        print(f"[simulation-orchestrator] ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
    finally:
        if world_scheduler is not None:
            try:
                world_scheduler.stop()
            except Exception as exc:
                print(f"[simulation-orchestrator] World cleanup warning: {exc}", file=sys.stderr)
        if camera_scheduler is not None:
            try:
                camera_scheduler.close()
            except Exception as exc:
                print(f"[simulation-orchestrator] Camera cleanup warning: {exc}", file=sys.stderr)
        simulation_app.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
