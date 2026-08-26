"""Top-level scheduler for deterministic moving-excavator semantic capture."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any, Iterator

from capture_launch_config import CaptureLaunchConfig
from capture_context import (
    CaptureContext,
    CaptureOperation,
    CaptureReceipt,
    CaptureVariant,
    ProbeReceipt,
)
from capture_timing import CaptureTiming
from isolated_render_config import IsolatedRenderConfig
from joint_control_profile import JointControlProfile
from render_profile import (
    RenderProfile,
    RenderProfileApplicationError,
    RenderProfileManager,
)
from stage_preflight import StagePreflight, file_record


RUN_CONFIG_SCHEMA_VERSION = 7


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schedule fixed-step world physics and synchronized semantic-camera capture"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="JSON file containing every semantic-capture business parameter",
    )
    return parser.parse_args(argv)


def resolve_renderer_selection(requested_renderer: str | None, profile: RenderProfile) -> str:
    """Resolve the single authoritative renderer and reject conflicting inputs."""
    if requested_renderer is not None and requested_renderer != profile.renderer:
        raise ValueError(
            f"Configured renderer {requested_renderer!r} conflicts with render profile "
            f"renderer {profile.renderer!r}: {profile.source_path}"
        )
    return profile.renderer


def validate_args(
    args: CaptureLaunchConfig,
    profile: RenderProfile,
    joint_profile: JointControlProfile,
) -> CaptureTiming:
    for label, path in (
        ("USD", args.usd),
        ("semantic mapping", args.mapping),
        ("render profile", args.render_profile),
        ("joint-control profile", args.joint_profile),
    ):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{label} file not found: {path}")
    if args.frames <= 0 or args.width <= 0 or args.height <= 0:
        raise ValueError("frames, width, and height must be positive")
    if profile.warmup_render_frames < 0 or args.pre_roll_steps < 0:
        raise ValueError("warmup_render_frames and pre_roll_steps must be non-negative")
    if args.articulation_ready_timeout_steps <= 0:
        raise ValueError("articulation-ready-timeout-steps must be positive")
    motion_enabled = args.capture_mode == "motion" and args.enable_motion
    if motion_enabled and not os.path.isfile(args.trajectory):
        raise FileNotFoundError(f"Trajectory CSV not found: {args.trajectory}")
    if profile.rt_subframes <= 0:
        raise ValueError("Resolved render profile must use positive rt_subframes")
    if tuple(joint_profile.logical_joint_names) != ("cab", "boom", "small_arm", "bucket"):
        raise ValueError("Joint-control profile must use cab, boom, small_arm, bucket order")
    return CaptureTiming(
        physics_hz=args.physics_hz,
        capture_fps=args.capture_fps,
        capture_initial_frame=args.capture_initial_frame,
        static=args.capture_mode == "static",
    )


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


def update_source_stage_integrity(
    manifest: dict[str, Any],
    source_stage: str | Path,
) -> dict[str, Any]:
    """Record whether the persistent source USD stayed byte/metadata identical."""
    initial = manifest["inputs"]["source_stage"]
    current = file_record(source_stage)
    compared_fields = ("exists", "size", "mtime_ns", "sha256")
    unchanged = all(initial.get(field) == current.get(field) for field in compared_fields)
    result = {
        "unchanged": bool(unchanged),
        "compared_fields": list(compared_fields),
        "initial": initial,
        "current": current,
    }
    manifest["source_stage_integrity"] = result
    return result


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


class VariantSettleError(RuntimeError):
    """Raised when Render/Annotator data never converges to a requested variant."""


def assert_camera_matches_context(camera_scheduler: Any, context: CaptureContext) -> None:
    current = tuple(camera_scheduler.get_state()["world_transform"])
    if current != tuple(context.camera_world_transform):
        raise RuntimeError(
            f"Camera world transform changed during frozen frame {context.frame_id}"
        )


def settle_variant(
    *,
    camera_scheduler: Any,
    world_scheduler: Any,
    frozen_world: Any,
    variant_controller: Any,
    base_context: CaptureContext,
    target_variant: CaptureVariant,
    settle_render_count: int,
    settle_rt_subframes: int,
    maximum_settle_attempts: int,
    probe_sequence: Iterator[int],
) -> tuple[Any, tuple[ProbeReceipt, ...]]:
    """Switch a variant and prove the real Annotator stream matches it."""
    transition_report = variant_controller.transition_to(target_variant)
    all_probes: list[ProbeReceipt] = []

    for attempt in range(1, maximum_settle_attempts + 1):
        if attempt > 1:
            transition_report = variant_controller.force_reapply(target_variant)
            world_scheduler.assert_still_frozen(frozen_world)
            assert_camera_matches_context(camera_scheduler, base_context)
            if attempt == maximum_settle_attempts:
                camera_scheduler.reconnect_annotators()
                world_scheduler.assert_still_frozen(frozen_world)
                assert_camera_matches_context(camera_scheduler, base_context)
        generation = variant_controller.visibility_generation
        camera_scheduler.reset_render_history()
        attempt_probes: list[ProbeReceipt] = []
        for _ in range(settle_render_count):
            world_scheduler.assert_still_frozen(frozen_world)
            assert_camera_matches_context(camera_scheduler, base_context)
            probe_context = replace(
                base_context,
                variant=target_variant,
                operation=CaptureOperation.PROBE,
                visibility_generation=generation,
                attempt=attempt,
                probe_index=next(probe_sequence),
            )
            probe_receipt = camera_scheduler.probe(
                probe_context,
                rt_subframes=settle_rt_subframes,
            )
            attempt_probes.append(probe_receipt)
            all_probes.append(probe_receipt)
            world_scheduler.assert_still_frozen(frozen_world)
            assert_camera_matches_context(camera_scheduler, base_context)

        last_probe = attempt_probes[-1]
        if last_probe.validation_passed:
            variant_controller.assert_state(
                target_variant,
                expected_generation=generation,
            )
            return transition_report, tuple(all_probes)

    last_errors = all_probes[-1].validation_errors if all_probes else ()
    generation = variant_controller.visibility_generation
    raise VariantSettleError(
        f"Scene variant {target_variant.value} did not settle for frame "
        f"{base_context.frame_id}/g{generation} after "
        f"{maximum_settle_attempts} attempt(s): "
        + ("; ".join(last_errors) if last_errors else "no valid ProbeReceipt")
    )


def capture_variant_to_staging(
    *,
    camera_scheduler: Any,
    world_scheduler: Any,
    frozen_world: Any,
    variant_controller: Any,
    base_context: CaptureContext,
    variant: CaptureVariant,
    settle_attempts_before_capture: int,
) -> CaptureReceipt:
    """Capture one validated variant without publishing the frame yet."""
    variant_controller.assert_state(
        variant,
        expected_generation=variant_controller.visibility_generation,
    )
    context = replace(
        base_context,
        variant=variant,
        operation=CaptureOperation.CAPTURE,
        visibility_generation=variant_controller.visibility_generation,
        attempt=0,
        probe_index=0,
        settle_attempts_before_capture=settle_attempts_before_capture,
    )
    world_scheduler.assert_still_frozen(frozen_world)
    assert_camera_matches_context(camera_scheduler, context)
    receipt = camera_scheduler.capture(context)
    world_scheduler.assert_still_frozen(frozen_world)
    assert_camera_matches_context(camera_scheduler, context)
    if receipt.frame_id != context.frame_id or receipt.variant is not context.variant:
        raise RuntimeError("Writer returned a CaptureReceipt for the wrong frame or variant")
    if receipt.visibility_generation != context.visibility_generation:
        raise RuntimeError(
            "Writer returned a CaptureReceipt for the wrong visibility generation"
        )
    if (
        receipt.settle_attempts_before_capture
        != context.settle_attempts_before_capture
    ):
        raise RuntimeError(
            "Writer returned a CaptureReceipt with the wrong settle-attempt count"
        )
    if not receipt.validation_passed:
        raise RuntimeError("Writer returned an unvalidated formal CaptureReceipt")
    return receipt


def base_manifest(
    args: CaptureLaunchConfig,
    excavator_only_render_config: IsolatedRenderConfig | None,
    front_teeth_only_render_config: IsolatedRenderConfig | None,
    profile: RenderProfile,
    joint_profile: JointControlProfile,
    trajectory_metadata: dict[str, Any] | None,
    timing: CaptureTiming,
    output_path: Path,
    original_argv: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": RUN_CONFIG_SCHEMA_VERSION,
        "status": "running",
        "started_at_utc": utc_now(),
        "command_line": original_argv,
        "launch_config": {
            "source": file_record(args.source_path),
            "schema_version": args.schema_version,
        },
        "effective_config": {
            **args.to_dict(),
            "renderer": profile.renderer,
            "rt_subframes": profile.rt_subframes,
            "warmup_render_frames": profile.warmup_render_frames,
        },
        "source_stage": str(Path(args.usd).resolve()),
        "semantic_mapping": str(Path(args.mapping).resolve()),
        "inputs": {
            "launch_config": file_record(args.source_path),
            "source_stage": file_record(args.usd),
            "semantic_mapping": file_record(args.mapping),
            "excavator_only_render_config": (
                file_record(excavator_only_render_config.source_path)
                if excavator_only_render_config is not None
                else None
            ),
            "front_teeth_only_render_config": (
                file_record(front_teeth_only_render_config.source_path)
                if front_teeth_only_render_config is not None
                else None
            ),
            "trajectory": file_record(args.trajectory)
            if args.capture_mode == "motion" and args.enable_motion
            else None,
            "trajectory_metadata": file_record(
                joint_profile.trajectory_metadata_path(args.trajectory)
            )
            if trajectory_metadata is not None
            else None,
            "joint_control_profile": file_record(args.joint_profile)
            if args.capture_mode == "motion" and args.enable_motion
            else None,
        },
        "output": str(output_path),
        "image_output_folders": {
            "full_scene_rgb": args.image_output_folders.full_scene_rgb,
            "full_scene_semantic": args.image_output_folders.full_scene_semantic,
            "excavator_only_rgb": args.image_output_folders.excavator_only_rgb,
            "excavator_only_semantic": args.image_output_folders.excavator_only_semantic,
            "front_teeth_only_rgb": args.image_output_folders.front_teeth_only_rgb,
            "front_teeth_only_semantic": args.image_output_folders.front_teeth_only_semantic,
        },
        "excavator_only_capture": {
            "enabled": bool(args.excavator_only_capture.enabled),
            "render_config": (
                excavator_only_render_config.to_dict()
                if excavator_only_render_config is not None
                else None
            ),
            "visibility_report": None,
        },
        "front_teeth_only_capture": {
            "enabled": bool(args.front_teeth_only_capture.enabled),
            "save_rgb": bool(args.front_teeth_only_capture.save_rgb),
            "render_config": (
                front_teeth_only_render_config.to_dict()
                if front_teeth_only_render_config is not None
                else None
            ),
            "visibility_report": None,
        },
        "frames": args.frames,
        "resolution": [args.width, args.height],
        "capture_mode": args.capture_mode,
        "camera": args.camera_prim_path,
        "physics_hz": args.physics_hz,
        "capture_fps": args.capture_fps,
        "physics_steps_per_capture": timing.steps_per_capture,
        "capture_initial_frame": bool(args.capture_initial_frame),
        "pre_roll_steps": args.pre_roll_steps,
        "motion_enabled": bool(args.capture_mode == "motion" and args.enable_motion),
        "motion_control": {
            "mode": "articulation_direct_position",
            "joint_profile": joint_profile.to_dict(),
            "trajectory_metadata": trajectory_metadata,
            "articulation_ready_timeout_steps": args.articulation_ready_timeout_steps,
            "bootstrap_steps": None,
            "setup_steps": None,
            "binding": None,
        },
        "rt_subframes": profile.rt_subframes,
        "warmup_render_frames": profile.warmup_render_frames,
        "warmup_updates": profile.warmup_render_frames,
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
    cli_args = parse_args()
    args = CaptureLaunchConfig.load(cli_args.config)
    profile = RenderProfile.load(args.render_profile).with_capture_overrides(
        rt_subframes=args.rt_subframes,
        warmup_render_frames=args.warmup_render_frames,
    )
    resolve_renderer_selection(args.renderer, profile)
    joint_profile = JointControlProfile.load(args.joint_profile)
    excavator_only_render_config = (
        IsolatedRenderConfig.load(
            args.excavator_only_capture.render_prim_paths_config
        )
        if args.excavator_only_capture.enabled
        and args.excavator_only_capture.render_prim_paths_config is not None
        else None
    )
    front_teeth_only_render_config = (
        IsolatedRenderConfig.load(
            args.front_teeth_only_capture.render_prim_paths_config
        )
        if args.front_teeth_only_capture.enabled
        and args.front_teeth_only_capture.render_prim_paths_config is not None
        else None
    )
    trajectory_metadata = (
        joint_profile.load_and_validate_trajectory_metadata(args.trajectory)
        if args.capture_mode == "motion" and args.enable_motion
        else None
    )
    timing = validate_args(args, profile, joint_profile)
    output_path = Path(args.output).resolve()
    ensure_output_path(output_path, args.overwrite)
    run_config_path = output_path / "run_config.json"
    manifest = base_manifest(
        args,
        excavator_only_render_config,
        front_teeth_only_render_config,
        profile,
        joint_profile,
        trajectory_metadata,
        timing,
        output_path,
        original_argv,
    )
    write_json_atomic(run_config_path, manifest)

    simulation_app = None
    camera_scheduler = None
    world_scheduler = None
    motion_scheduler = None
    scene_variant_controller = None
    exit_code = 0

    try:
        from isaacsim import SimulationApp

        simulation_app = SimulationApp(launch_config=profile.launch_config(args.headless))

        import carb.settings
        import omni.usd
        # These modules import Kit/Replicator APIs and therefore load after SimulationApp.
        from articulation_stage_validator import validate_articulation_stage
        from excavator_joint_motion import ExcavatorJointMotion
        from semantic_capture_custom import SemanticCameraScheduler
        from scene_visibility_controller import SceneVariantController
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

        camera_path = args.camera_prim_path
        preflight = StagePreflight(
            stage=stage,
            source_stage=args.usd,
            mapping_path=args.mapping,
            camera_path=camera_path,
            joint_specs=(),
        ).run()
        motion_enabled = args.capture_mode == "motion" and args.enable_motion
        articulation_report = (
            validate_articulation_stage(stage, joint_profile)
            if motion_enabled
            else None
        )
        if articulation_report is not None:
            preflight_payload = preflight.to_dict()
            preflight_payload["articulation"] = articulation_report.to_dict()
        else:
            preflight_payload = preflight.to_dict()
            preflight_payload["articulation"] = None
        manifest["preflight"] = preflight_payload
        manifest["warnings"] = [issue.to_dict() for issue in preflight.warnings]
        if articulation_report is not None:
            manifest["warnings"].extend(
                issue.to_dict() for issue in articulation_report.warnings
            )
        write_json_atomic(run_config_path, manifest)
        preflight.raise_if_unusable()
        preflight.raise_if_blocking(strict=args.strict_stage)
        if articulation_report is not None:
            articulation_report.require_valid()
        variant_prim_paths: dict[CaptureVariant, tuple[str, ...]] = {}
        if excavator_only_render_config is not None:
            variant_prim_paths[CaptureVariant.EXCAVATOR_ONLY] = tuple(
                excavator_only_render_config.render_prim_paths
            )
        if front_teeth_only_render_config is not None:
            variant_prim_paths[CaptureVariant.FRONT_TEETH_ONLY] = tuple(
                front_teeth_only_render_config.render_prim_paths
            )
        scene_variant_controller = SceneVariantController(
            stage=stage,
            variant_prim_paths=variant_prim_paths,
            protected_prim_paths=(camera_path,),
            layer_name="semantic_capture_visibility.usda",
            stage_update_callback=simulation_app.update,
        )
        manifest["scene_variant_controller"] = {
            "current_variant": scene_variant_controller.current_variant.value,
            "visibility_generation": scene_variant_controller.visibility_generation,
            "available_variants": [
                variant.value for variant in scene_variant_controller.available_variants
            ],
            "initial_report": scene_variant_controller.last_report.to_dict(),
            "persistent_usd_protection": (
                scene_variant_controller.protection_report()
            ),
        }

        maximum_data_step = max(
            timing.data_step_for_frame(frame_id) for frame_id in range(args.frames)
        )
        run_duration = (
            args.pre_roll_steps
            + maximum_data_step
            + (args.articulation_ready_timeout_steps + 1 if motion_enabled else 0)
        ) / float(args.physics_hz) + 1.0
        world_scheduler = WorldScheduler(
            simulation_app=simulation_app,
            stage=stage,
            physics_hz=args.physics_hz,
            maximum_duration_seconds=run_duration,
        )
        world_scheduler.initialize()

        if motion_enabled:
            motion_scheduler = ExcavatorJointMotion(
                stage=stage,
                trajectory_path=Path(args.trajectory).resolve(),
                joint_profile=joint_profile,
                stage_report=articulation_report,
                playback_mode=args.trajectory_mode,
                interpolation=args.interpolation,
                trajectory_metadata=trajectory_metadata,
            )
            # Wrapper creation and stable name-to-index binding happen before
            # Timeline playback; tensor-backed reads/writes are initialized below.
            motion_scheduler.bind()

        world_scheduler.start()
        if motion_scheduler is not None:
            bootstrap_steps = world_scheduler.bootstrap_until(
                predicate=lambda: motion_scheduler.ready,
                max_steps=args.articulation_ready_timeout_steps,
                description="Articulation physics tensor",
            )
            motion_scheduler.initialize_runtime()
            world_scheduler.advance_exact_steps(
                1,
                before_step_callback=lambda _time: motion_scheduler.apply_initial_positions(),
                after_step_callback=lambda _time: motion_scheduler.after_physics_step(0.0),
            )
            manifest["motion_control"]["bootstrap_steps"] = bootstrap_steps
            manifest["motion_control"]["setup_steps"] = 1
            manifest["motion_control"]["binding"] = motion_scheduler.binding_info()
        if args.pre_roll_steps:
            hold_initial_before = (
                (lambda _time: motion_scheduler.before_physics_step(0.0))
                if motion_scheduler is not None else None
            )
            hold_initial_after = (
                (lambda _time: motion_scheduler.after_physics_step(0.0))
                if motion_scheduler is not None else None
            )
            world_scheduler.advance_exact_steps(
                args.pre_roll_steps,
                before_step_callback=hold_initial_before,
                after_step_callback=hold_initial_after,
            )
        world_scheduler.begin_data_timeline()
        frozen_world = world_scheduler.freeze_for_capture()

        camera_scheduler = SemanticCameraScheduler(
            simulation_app=simulation_app,
            stage=stage,
            camera_path=camera_path,
            output_path=output_path,
            mapping_path=Path(args.mapping).resolve(),
            width=args.width,
            height=args.height,
            rt_subframes=profile.rt_subframes,
            save_runtime_ids=args.save_runtime_ids,
            strict_mapping=args.strict_mapping,
            output_folders=args.image_output_folders,
            transparent_isolated_background=(
                args.excavator_only_capture.enabled
                or args.front_teeth_only_capture.save_rgb
            ),
            save_front_teeth_only_rgb=args.front_teeth_only_capture.save_rgb,
            variant_validation=args.variant_validation,
            overwrite_output=args.overwrite,
        )
        camera_scheduler.initialize()
        camera_scheduler.warmup(profile.warmup_render_frames)
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
                scene_variant_controller.assert_state(CaptureVariant.FULL_SCENE)
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
                        before_step_callback=(
                            motion_scheduler.before_physics_step
                            if motion_scheduler is not None else None
                        ),
                        after_step_callback=(
                            motion_scheduler.after_physics_step
                            if motion_scheduler is not None else None
                        ),
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
                    variant=CaptureVariant.FULL_SCENE,
                    operation=CaptureOperation.CAPTURE,
                    visibility_generation=(
                        scene_variant_controller.visibility_generation
                    ),
                )
                probe_sequence = count()
                formal_receipts: list[CaptureReceipt] = []
                probe_receipts: dict[str, list[dict[str, Any]]] = {}
                try:
                    _report, probes = settle_variant(
                        camera_scheduler=camera_scheduler,
                        world_scheduler=world_scheduler,
                        frozen_world=frozen_world,
                        variant_controller=scene_variant_controller,
                        base_context=context,
                        target_variant=CaptureVariant.FULL_SCENE,
                        settle_render_count=args.variant_transition.settle_render_count,
                        settle_rt_subframes=args.variant_transition.settle_rt_subframes,
                        maximum_settle_attempts=(
                            args.variant_transition.maximum_settle_attempts
                        ),
                        probe_sequence=probe_sequence,
                    )
                    probe_receipts["full_scene_pre_capture"] = [
                        receipt.to_dict() for receipt in probes
                    ]
                    full_scene_receipt = capture_variant_to_staging(
                        camera_scheduler=camera_scheduler,
                        world_scheduler=world_scheduler,
                        frozen_world=frozen_world,
                        variant_controller=scene_variant_controller,
                        base_context=context,
                        variant=CaptureVariant.FULL_SCENE,
                        settle_attempts_before_capture=probes[-1].attempt,
                    )
                    formal_receipts.append(full_scene_receipt)

                    if excavator_only_render_config is not None:
                        transition_report, probes = settle_variant(
                            camera_scheduler=camera_scheduler,
                            world_scheduler=world_scheduler,
                            frozen_world=frozen_world,
                            variant_controller=scene_variant_controller,
                            base_context=context,
                            target_variant=CaptureVariant.EXCAVATOR_ONLY,
                            settle_render_count=(
                                args.variant_transition.settle_render_count
                            ),
                            settle_rt_subframes=(
                                args.variant_transition.settle_rt_subframes
                            ),
                            maximum_settle_attempts=(
                                args.variant_transition.maximum_settle_attempts
                            ),
                            probe_sequence=probe_sequence,
                        )
                        if (
                            manifest["excavator_only_capture"]["visibility_report"]
                            is None
                        ):
                            manifest["excavator_only_capture"][
                                "visibility_report"
                            ] = transition_report.to_dict()
                            write_json_atomic(run_config_path, manifest)
                        probe_receipts[CaptureVariant.EXCAVATOR_ONLY.value] = [
                            receipt.to_dict() for receipt in probes
                        ]
                        formal_receipts.append(
                            capture_variant_to_staging(
                                camera_scheduler=camera_scheduler,
                                world_scheduler=world_scheduler,
                                frozen_world=frozen_world,
                                variant_controller=scene_variant_controller,
                                base_context=context,
                                variant=CaptureVariant.EXCAVATOR_ONLY,
                                settle_attempts_before_capture=probes[-1].attempt,
                            )
                        )

                    if front_teeth_only_render_config is not None:
                        transition_report, probes = settle_variant(
                            camera_scheduler=camera_scheduler,
                            world_scheduler=world_scheduler,
                            frozen_world=frozen_world,
                            variant_controller=scene_variant_controller,
                            base_context=context,
                            target_variant=CaptureVariant.FRONT_TEETH_ONLY,
                            settle_render_count=(
                                args.variant_transition.settle_render_count
                            ),
                            settle_rt_subframes=(
                                args.variant_transition.settle_rt_subframes
                            ),
                            maximum_settle_attempts=(
                                args.variant_transition.maximum_settle_attempts
                            ),
                            probe_sequence=probe_sequence,
                        )
                        if (
                            manifest["front_teeth_only_capture"]["visibility_report"]
                            is None
                        ):
                            manifest["front_teeth_only_capture"][
                                "visibility_report"
                            ] = transition_report.to_dict()
                            write_json_atomic(run_config_path, manifest)
                        probe_receipts[CaptureVariant.FRONT_TEETH_ONLY.value] = [
                            receipt.to_dict() for receipt in probes
                        ]
                        formal_receipts.append(
                            capture_variant_to_staging(
                                camera_scheduler=camera_scheduler,
                                world_scheduler=world_scheduler,
                                frozen_world=frozen_world,
                                variant_controller=scene_variant_controller,
                                base_context=context,
                                variant=CaptureVariant.FRONT_TEETH_ONLY,
                                settle_attempts_before_capture=probes[-1].attempt,
                            )
                        )

                    _report, probes = settle_variant(
                        camera_scheduler=camera_scheduler,
                        world_scheduler=world_scheduler,
                        frozen_world=frozen_world,
                        variant_controller=scene_variant_controller,
                        base_context=context,
                        target_variant=CaptureVariant.FULL_SCENE,
                        settle_render_count=args.variant_transition.settle_render_count,
                        settle_rt_subframes=args.variant_transition.settle_rt_subframes,
                        maximum_settle_attempts=(
                            args.variant_transition.maximum_settle_attempts
                        ),
                        probe_sequence=probe_sequence,
                    )
                    probe_receipts["full_scene_restore"] = [
                        receipt.to_dict() for receipt in probes
                    ]
                    scene_variant_controller.assert_state(CaptureVariant.FULL_SCENE)
                    world_scheduler.assert_still_frozen(frozen_world)
                    assert_camera_matches_context(camera_scheduler, context)
                    camera_scheduler.wait_until_complete()
                    expected_variants = {CaptureVariant.FULL_SCENE}
                    if excavator_only_render_config is not None:
                        expected_variants.add(CaptureVariant.EXCAVATOR_ONLY)
                    if front_teeth_only_render_config is not None:
                        expected_variants.add(CaptureVariant.FRONT_TEETH_ONLY)
                    actual_variants = {
                        receipt.variant for receipt in formal_receipts
                    }
                    if actual_variants != expected_variants:
                        raise RuntimeError(
                            f"Frame {frame_id} formal variants do not match: "
                            f"{sorted(item.value for item in actual_variants)} != "
                            f"{sorted(item.value for item in expected_variants)}"
                        )
                    camera_scheduler.commit_frame(frame_id, formal_receipts)
                except Exception:
                    try:
                        settle_variant(
                            camera_scheduler=camera_scheduler,
                            world_scheduler=world_scheduler,
                            frozen_world=frozen_world,
                            variant_controller=scene_variant_controller,
                            base_context=context,
                            target_variant=CaptureVariant.FULL_SCENE,
                            settle_render_count=(
                                args.variant_transition.settle_render_count
                            ),
                            settle_rt_subframes=(
                                args.variant_transition.settle_rt_subframes
                            ),
                            maximum_settle_attempts=(
                                args.variant_transition.maximum_settle_attempts
                            ),
                            probe_sequence=probe_sequence,
                        )
                    except Exception as recovery_exc:
                        print(
                            f"[simulation-orchestrator] Frame {frame_id} full-scene "
                            f"recovery warning: {recovery_exc}",
                            file=sys.stderr,
                        )
                    try:
                        camera_scheduler.discard_frame(frame_id)
                    except Exception as discard_exc:
                        print(
                            f"[simulation-orchestrator] Frame {frame_id} staging "
                            f"cleanup warning: {discard_exc}",
                            file=sys.stderr,
                        )
                    raise

                capture_receipts = {
                    receipt.variant.value: receipt.to_dict()
                    for receipt in formal_receipts
                }

                state = {
                    **context.to_dict(),
                    "simulation_time": world_scheduler.simulation_time,
                    "world": world_scheduler.get_state(),
                    "camera": camera_state,
                    "motion": motion_state,
                    "capture_receipt": full_scene_receipt.to_dict(),
                    "capture_receipts": capture_receipts,
                    "probe_receipts": probe_receipts,
                    "frame_committed": True,
                    "end_variant": scene_variant_controller.current_variant.value,
                    "end_visibility_generation": (
                        scene_variant_controller.visibility_generation
                    ),
                    "writer_pending": camera_scheduler.statistics()["pending"],
                }
                motion_stream.write(json.dumps(state, ensure_ascii=False) + "\n")
                motion_stream.flush()
                print(
                    f"[simulation-orchestrator] Captured frame {frame_id + 1}/{args.frames} "
                    f"at dataset_t={expected_time:.6f}s, "
                    f"timeline_t={frozen_world.timeline_time:.6f}s, "
                    f"variants={','.join(capture_receipts)}"
                )

        camera_scheduler.wait_until_complete()
        scene_variant_controller.assert_persistent_layers_pristine()
        integrity = update_source_stage_integrity(manifest, args.usd)
        if not integrity["unchanged"]:
            raise RuntimeError(
                "Persistent source USD changed during capture; refusing to mark run complete"
            )
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
            update_source_stage_integrity(manifest, args.usd)
        except Exception as integrity_exc:
            manifest["source_stage_integrity"] = {
                "unchanged": False,
                "error": str(integrity_exc),
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
        visibility_cleanup_error: Exception | None = None
        for visibility_controller in (scene_variant_controller,):
            if visibility_controller is None:
                continue
            try:
                visibility_controller.close()
            except Exception as exc:
                visibility_cleanup_error = exc
                print(
                    f"[simulation-orchestrator] Visibility cleanup warning: {exc}",
                    file=sys.stderr,
                )
        try:
            integrity = update_source_stage_integrity(manifest, args.usd)
            if not integrity["unchanged"] or visibility_cleanup_error is not None:
                exit_code = 1
                manifest["status"] = "failed"
                manifest["failed_at_utc"] = utc_now()
                if not integrity["unchanged"]:
                    manifest["error"] = {
                        "type": "PersistentSourceMutationError",
                        "message": "Persistent source USD changed during capture",
                    }
                elif visibility_cleanup_error is not None:
                    manifest["error"] = {
                        "type": type(visibility_cleanup_error).__name__,
                        "message": str(visibility_cleanup_error),
                    }
            write_json_atomic(run_config_path, manifest)
        except Exception as integrity_exc:
            exit_code = 1
            print(
                f"[simulation-orchestrator] Source USD integrity warning: {integrity_exc}",
                file=sys.stderr,
            )
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
        if motion_scheduler is not None:
            try:
                motion_scheduler.shutdown()
            except Exception as exc:
                print(f"[simulation-orchestrator] Motion cleanup warning: {exc}", file=sys.stderr)
        if simulation_app is not None:
            simulation_app.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
