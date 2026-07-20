"""Top-level scheduler for deterministic moving-excavator semantic capture."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capture_context import CaptureContext
from capture_timing import CaptureTiming
from render_profile import (
    RenderProfile,
    RenderProfileApplicationError,
    RenderProfileManager,
    SUPPORTED_RENDERERS,
)
from stage_preflight import StagePreflight, file_record


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_STAGE = PROJECT_DIR / "configs" / "usd_ply_combined_02_capture_overlay.usda"
DEFAULT_MAPPING = PROJECT_DIR / "configs" / "semantic_mapping_usd_ply_combined_02.json"
DEFAULT_TRAJECTORY = PROJECT_DIR / "trajectories" / "excavator_motion_01.csv"
DEFAULT_RENDERER = "RealTimePathTracing"
DEFAULT_RENDER_PROFILES = {
    "RealTimePathTracing": PROJECT_DIR / "configs" / "render_realtime_pathtracing_720p.json",
    "PathTracing": PROJECT_DIR / "configs" / "render_pathtracing_720p_64spp.json",
}
DEFAULT_RENDER_PROFILE = DEFAULT_RENDER_PROFILES[DEFAULT_RENDERER]
DEFAULT_OUTPUT = PROJECT_DIR / "output" / "semantic_capture_v2"
RUN_CONFIG_SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Schedule fixed-step world physics and synchronized semantic-camera capture"
    )
    parser.add_argument("--usd", default=str(DEFAULT_STAGE), help="USD or USDA stage to open")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING), help="Stable semantic mapping JSON")
    parser.add_argument(
        "--renderer",
        choices=SUPPORTED_RENDERERS,
        default=None,
        help="RTX renderer; selects its default profile when --render-profile is omitted",
    )
    parser.add_argument(
        "--render-profile",
        default=None,
        help="Versioned render profile; its renderer must match an explicit --renderer",
    )
    parser.add_argument(
        "--camera",
        default="/root/Xform/operator_cab_mesh/Camera_01",
        help="Camera prim path; empty discovers the only Camera below --cab-root",
    )
    parser.add_argument("--cab-root", default="/root/Xform/operator_cab_mesh")
    parser.add_argument(
        "--require-camera-below-cab",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable only for explicit static diagnostics such as /root/Camera_03",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument(
        "--warmup",
        "--warmup-render-frames",
        dest="warmup_render_frames",
        type=int,
        default=None,
        help="Override the selected render profile's warm-up frame count",
    )
    parser.add_argument(
        "--rt-subframes",
        type=int,
        default=None,
        help="Override the render profile's RT subframe count",
    )
    parser.add_argument("--physics-hz", type=int, default=60)
    parser.add_argument("--capture-fps", type=int, default=10)
    parser.add_argument("--capture-mode", choices=("static", "motion"), default="motion")
    parser.add_argument(
        "--capture-initial-frame",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When enabled, frame 0000 is captured at dataset time zero",
    )
    parser.add_argument("--pre-roll-steps", type=int, default=0)
    parser.add_argument(
        "--trajectory",
        default=str(DEFAULT_TRAJECTORY),
        help="CSV keyframes with columns: time,cab,boom,small_arm,bucket",
    )
    parser.add_argument(
        "--trajectory-mode",
        choices=("loop", "hold"),
        default="loop",
    )
    parser.add_argument("--interpolation", choices=("linear",), default="linear")
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
        "--strict-stage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Block production capture when Stage preflight reports errors",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow writing into a non-empty output directory",
    )
    return parser.parse_known_args(argv)


def choose_default_render_profile(args: argparse.Namespace) -> None:
    """Select a default profile only when the user did not provide one."""
    if args.render_profile is not None:
        return
    renderer = args.renderer or DEFAULT_RENDERER
    args.render_profile = str(DEFAULT_RENDER_PROFILES[renderer])


def resolve_renderer_selection(requested_renderer: str | None, profile: RenderProfile) -> str:
    """Resolve the single authoritative renderer and reject conflicting inputs."""
    if requested_renderer is not None and requested_renderer != profile.renderer:
        raise ValueError(
            f"--renderer {requested_renderer!r} conflicts with render profile "
            f"renderer {profile.renderer!r}: {profile.source_path}"
        )
    return profile.renderer


def validate_args(args: argparse.Namespace, profile: RenderProfile) -> CaptureTiming:
    for label, path in (
        ("USD", args.usd),
        ("semantic mapping", args.mapping),
        ("render profile", args.render_profile),
    ):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{label} file not found: {path}")
    if args.frames <= 0 or args.width <= 0 or args.height <= 0:
        raise ValueError("frames, width, and height must be positive")
    if args.warmup_render_frames < 0 or args.pre_roll_steps < 0:
        raise ValueError("warmup-render-frames and pre-roll-steps must be non-negative")
    motion_enabled = args.capture_mode == "motion" and args.enable_motion
    if motion_enabled and not os.path.isfile(args.trajectory):
        raise FileNotFoundError(f"Trajectory CSV not found: {args.trajectory}")
    if profile.rt_subframes <= 0:
        raise ValueError("Resolved render profile must use positive rt_subframes")
    return CaptureTiming(
        physics_hz=args.physics_hz,
        capture_fps=args.capture_fps,
        capture_initial_frame=args.capture_initial_frame,
        static=args.capture_mode == "static",
    )


def resolve_project_relative_paths(args: argparse.Namespace) -> None:
    """Resolve CLI file paths consistently despite run_capture_remote.sh changing cwd."""
    for attribute in ("usd", "mapping", "render_profile", "trajectory", "output"):
        raw_value = getattr(args, attribute)
        if raw_value is None:
            continue
        value = Path(raw_value).expanduser()
        if not value.is_absolute():
            value = PROJECT_DIR / value
        setattr(args, attribute, str(value.resolve()))


def ensure_output_path(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {path}. Choose a new path or pass --overwrite."
        )
    path.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, value: Any) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary_path.replace(path)


def resolve_camera_path(stage: Any, requested: str, cab_root: str) -> str:
    if requested:
        return requested
    from pxr import Usd, UsdGeom

    cab_prim = stage.GetPrimAtPath(cab_root)
    cameras = [
        str(prim.GetPath())
        for prim in Usd.PrimRange(cab_prim)
        if prim.IsA(UsdGeom.Camera)
    ]
    if len(cameras) != 1:
        raise RuntimeError(f"Expected one Camera below {cab_root}, found {cameras}")
    return cameras[0]


def wait_for_opened_stage(simulation_app: Any, stage_path: str, max_updates: int = 600) -> Any:
    """Wait until omni.usd exposes a composed stage with at least one root prim."""
    import omni.usd

    context = omni.usd.get_context()
    last_status: Any = None
    for update_index in range(max_updates):
        simulation_app.update()
        stage = context.get_stage()
        last_status = context.get_stage_loading_status()
        pending = int(last_status[2]) if len(last_status) > 2 else 0
        if stage is not None:
            root_layer = stage.GetRootLayer()
            real_path = str(getattr(root_layer, "realPath", "") or "")
            source_matches = not real_path or Path(real_path).resolve() == Path(stage_path).resolve()
            if source_matches and pending == 0 and stage.GetPseudoRoot().GetChildren():
                print(
                    f"[simulation-orchestrator] Stage composition ready after "
                    f"{update_index + 1} update(s)"
                )
                return stage
    raise RuntimeError(
        f"Stage did not become composition-ready after {max_updates} updates; "
        f"loading_status={last_status}"
    )


def base_manifest(
    args: argparse.Namespace,
    profile: RenderProfile,
    timing: CaptureTiming,
    output_path: Path,
    original_argv: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": RUN_CONFIG_SCHEMA_VERSION,
        "status": "running",
        "started_at_utc": utc_now(),
        "command_line": original_argv,
        "source_stage": str(Path(args.usd).resolve()),
        "semantic_mapping": str(Path(args.mapping).resolve()),
        "inputs": {
            "source_stage": file_record(args.usd),
            "semantic_mapping": file_record(args.mapping),
            "trajectory": file_record(args.trajectory)
            if args.capture_mode == "motion" and args.enable_motion
            else None,
        },
        "output": str(output_path),
        "frames": args.frames,
        "resolution": [args.width, args.height],
        "capture_mode": args.capture_mode,
        "camera": args.camera,
        "cab_root": args.cab_root,
        "require_camera_below_cab": bool(args.require_camera_below_cab),
        "physics_hz": args.physics_hz,
        "capture_fps": args.capture_fps,
        "physics_steps_per_capture": timing.steps_per_capture,
        "capture_initial_frame": bool(args.capture_initial_frame),
        "pre_roll_steps": args.pre_roll_steps,
        "motion_enabled": bool(args.capture_mode == "motion" and args.enable_motion),
        "rt_subframes": profile.rt_subframes,
        "warmup_render_frames": args.warmup_render_frames,
        "warmup_updates": args.warmup_render_frames,
        "save_runtime_ids": bool(args.save_runtime_ids),
        "strict_mapping": bool(args.strict_mapping),
        "strict_stage": bool(args.strict_stage),
        "render": {
            "profile": profile.to_dict(),
            "renderer": {"requested": profile.renderer, "effective": None},
            "launch": dict(profile.launch_settings),
            "capture": dict(profile.capture_settings),
            "sampling": profile.sampling_summary(),
            "mismatches": [],
        },
        "software": {
            "python": sys.version,
            "platform": platform.platform(),
        },
        "warnings": [],
    }


def main() -> int:
    original_argv = list(sys.argv)
    args, kit_args = parse_args()
    choose_default_render_profile(args)
    resolve_project_relative_paths(args)
    profile = RenderProfile.load(args.render_profile).with_capture_overrides(
        rt_subframes=args.rt_subframes,
        warmup_render_frames=args.warmup_render_frames,
    )
    args.renderer = resolve_renderer_selection(args.renderer, profile)
    args.warmup_render_frames = profile.warmup_render_frames
    timing = validate_args(args, profile)
    output_path = Path(args.output).resolve()
    ensure_output_path(output_path, args.overwrite)
    run_config_path = output_path / "run_config.json"
    manifest = base_manifest(args, profile, timing, output_path, original_argv)
    write_json_atomic(run_config_path, manifest)

    # Kit consumes only arguments that argparse did not recognize.
    sys.argv = [original_argv[0], *kit_args]
    simulation_app = None
    camera_scheduler = None
    world_scheduler = None
    exit_code = 0

    try:
        from isaacsim import SimulationApp

        simulation_app = SimulationApp(launch_config=profile.launch_config(args.headless))

        import carb.settings
        import omni.usd
        # These modules import Kit/Replicator APIs and therefore load after SimulationApp.
        from excavator_joint_motion import ExcavatorJointMotion, JOINT_SPECS
        from semantic_capture_custom import SemanticCameraScheduler
        from world_scheduler import WorldScheduler

        print(f"[simulation-orchestrator] Loading stage: {args.usd}")
        if not omni.usd.get_context().open_stage(args.usd):
            raise RuntimeError(f"Failed to open USD stage: {args.usd}")
        stage = wait_for_opened_stage(simulation_app, args.usd)

        # Opening a Stage can author or restore a different render mode. Re-apply
        # the selected SimulationApp renderer once, then enforce and read back the
        # profile's required Carb settings.
        simulation_app.reset_render_settings()
        try:
            render_snapshot = RenderProfileManager(
                carb.settings.get_settings()
            ).apply_and_snapshot(profile)
        except RenderProfileApplicationError as exc:
            manifest["render"] = exc.snapshot
            write_json_atomic(run_config_path, manifest)
            raise
        manifest["render"] = render_snapshot

        camera_path = resolve_camera_path(stage, args.camera, args.cab_root)
        preflight = StagePreflight(
            stage=stage,
            source_stage=args.usd,
            mapping_path=args.mapping,
            camera_path=camera_path,
            cab_root=args.cab_root,
            require_camera_below_cab=args.require_camera_below_cab,
            joint_specs=JOINT_SPECS if args.capture_mode == "motion" else (),
        ).run()
        manifest["preflight"] = preflight.to_dict()
        manifest["warnings"] = [issue.to_dict() for issue in preflight.warnings]
        write_json_atomic(run_config_path, manifest)
        preflight.raise_if_unusable()
        preflight.raise_if_blocking(strict=args.strict_stage)

        maximum_data_step = max(
            timing.data_step_for_frame(frame_id) for frame_id in range(args.frames)
        )
        run_duration = (
            args.pre_roll_steps + maximum_data_step
        ) / float(args.physics_hz) + 1.0
        world_scheduler = WorldScheduler(
            simulation_app=simulation_app,
            stage=stage,
            physics_hz=args.physics_hz,
            maximum_duration_seconds=run_duration,
        )
        world_scheduler.initialize()

        motion_enabled = args.capture_mode == "motion" and args.enable_motion
        motion_scheduler = None
        if motion_enabled:
            motion_scheduler = ExcavatorJointMotion(
                stage=stage,
                trajectory_path=Path(args.trajectory).resolve(),
                playback_mode=args.trajectory_mode,
                interpolation=args.interpolation,
                safety_margin_degrees=2.0,
            )
            motion_scheduler.initialize()
            motion_scheduler.apply_initial_targets()

        world_scheduler.start()
        if args.pre_roll_steps:
            hold_initial = (
                (lambda _dataset_time: motion_scheduler.update(0.0))
                if motion_scheduler is not None
                else None
            )
            world_scheduler.advance_exact_steps(args.pre_roll_steps, hold_initial)
        world_scheduler.begin_data_timeline()
        frozen_world = world_scheduler.freeze_for_capture()

        camera_scheduler = SemanticCameraScheduler(
            simulation_app=simulation_app,
            stage=stage,
            camera_path=camera_path,
            cab_root=args.cab_root,
            output_path=output_path,
            mapping_path=Path(args.mapping).resolve(),
            width=args.width,
            height=args.height,
            rt_subframes=profile.rt_subframes,
            save_runtime_ids=args.save_runtime_ids,
            strict_mapping=args.strict_mapping,
            require_camera_below_cab=args.require_camera_below_cab,
        )
        camera_scheduler.initialize()
        camera_scheduler.warmup(args.warmup_render_frames)
        world_scheduler.assert_still_frozen(frozen_world)
        camera_scheduler.attach_writer()

        manifest["camera"] = camera_scheduler.camera_path
        manifest["camera_initial_state"] = camera_scheduler.get_state()
        if motion_scheduler is not None:
            manifest["trajectory"] = motion_scheduler.trajectory_info()
            manifest["joints"] = motion_scheduler.describe()
        write_json_atomic(run_config_path, manifest)

        print(
            f"[simulation-orchestrator] Running {args.frames} capture(s), "
            f"mode={args.capture_mode}, physics={args.physics_hz} Hz, "
            f"camera={args.capture_fps} FPS, steps/capture={timing.steps_per_capture}, "
            f"renderer={profile.renderer}, rt_subframes={profile.rt_subframes}"
        )

        motion_state_path = output_path / "motion_state.jsonl"
        with motion_state_path.open("w", encoding="utf-8") as motion_stream:
            for frame_id in range(args.frames):
                target_data_step = timing.data_step_for_frame(frame_id)
                steps_to_advance = target_data_step - world_scheduler.dataset_step
                if steps_to_advance < 0:
                    raise RuntimeError(
                        f"Capture schedule moved backwards at frame {frame_id}: "
                        f"target={target_data_step}, current={world_scheduler.dataset_step}"
                    )
                if steps_to_advance:
                    world_scheduler.resume_after_capture()
                    world_scheduler.advance_exact_steps(
                        steps_to_advance,
                        motion_scheduler.update if motion_scheduler is not None else None,
                    )
                    frozen_world = world_scheduler.freeze_for_capture()
                else:
                    frozen_world = world_scheduler.freeze_for_capture()

                expected_time = timing.dataset_time_for_frame(frame_id)
                if abs(world_scheduler.dataset_time - expected_time) > 1e-9:
                    raise RuntimeError(
                        f"Dataset time mismatch at frame {frame_id}: "
                        f"expected={expected_time}, actual={world_scheduler.dataset_time}"
                    )

                camera_state = camera_scheduler.get_state()
                motion_state = (
                    motion_scheduler.get_state(expected_time)
                    if motion_scheduler is not None
                    else {"enabled": False}
                )
                context = CaptureContext(
                    frame_id=frame_id,
                    dataset_time=expected_time,
                    timeline_time=frozen_world.timeline_time,
                    physics_step=frozen_world.physics_step,
                    camera_path=camera_scheduler.camera_path,
                    camera_world_transform=tuple(camera_state["world_transform"]),
                    motion_state=motion_state,
                )
                world_scheduler.assert_still_frozen(frozen_world)
                receipt = camera_scheduler.capture(context)
                world_scheduler.assert_still_frozen(frozen_world)

                state = {
                    **context.to_dict(),
                    "simulation_time": world_scheduler.simulation_time,
                    "world": world_scheduler.get_state(),
                    "camera": camera_state,
                    "motion": motion_state,
                    "capture_receipt": receipt.to_dict(),
                }
                motion_stream.write(json.dumps(state, ensure_ascii=False) + "\n")
                motion_stream.flush()
                print(
                    f"[simulation-orchestrator] Captured frame {frame_id + 1}/{args.frames} "
                    f"at dataset_t={expected_time:.6f}s, timeline_t={frozen_world.timeline_time:.6f}s"
                )

        camera_scheduler.wait_until_complete()
        manifest["writer"] = camera_scheduler.statistics()
        manifest["status"] = "complete"
        manifest["completed_at_utc"] = utc_now()
        write_json_atomic(run_config_path, manifest)
        print(f"[semantic-capture] Complete: {output_path}")
    except Exception as exc:
        exit_code = 1
        manifest["status"] = "failed"
        manifest["failed_at_utc"] = utc_now()
        manifest["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        try:
            write_json_atomic(run_config_path, manifest)
        except Exception as manifest_exc:
            print(
                f"[simulation-orchestrator] Manifest update warning: {manifest_exc}",
                file=sys.stderr,
            )
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
        if simulation_app is not None:
            simulation_app.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
