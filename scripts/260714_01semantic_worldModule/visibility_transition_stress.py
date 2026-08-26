"""Same-process Hydra/semantic visibility transition endurance diagnostic.

The diagnostic intentionally publishes no dataset frames.  It drives the same
moving Stage, persistent RenderProduct, semantic annotators, visibility
controller, and validation rules used by the formal capture pipeline, while
repeating excavator-only -> front-teeth-only -> full-scene transitions.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any

from capture_context import CaptureContext, CaptureOperation, CaptureVariant
from capture_launch_config import CaptureLaunchConfig
from isolated_render_config import IsolatedRenderConfig
from joint_control_profile import JointControlProfile
from render_profile import RenderProfile, RenderProfileManager
from simulation_orchestrator import (
    assert_camera_matches_context,
    settle_variant,
    validate_args,
    wait_for_opened_stage,
    write_json_atomic,
)
from stage_preflight import StagePreflight, file_record


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise semantic scene visibility transitions in one Isaac Sim "
            "process without publishing capture frames"
        )
    )
    parser.add_argument("--config", required=True, help="Capture JSON to exercise")
    parser.add_argument("--cycles", type=int, default=700)
    parser.add_argument("--output", required=True, help="Empty diagnostic output folder")
    parser.add_argument("--rt-subframes", type=int, default=1)
    parser.add_argument("--boundary-start-generation", type=int, default=2040)
    parser.add_argument("--boundary-rt-subframes", type=int, default=16)
    parser.add_argument("--progress-every", type=int, default=25)
    parsed = parser.parse_args(argv)
    for name in (
        "cycles",
        "rt_subframes",
        "boundary_start_generation",
        "boundary_rt_subframes",
        "progress_every",
    ):
        if getattr(parsed, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    return parsed


def source_records_equal(initial: dict[str, Any], current: dict[str, Any]) -> bool:
    fields = ("exists", "size", "mtime_ns", "sha256")
    return all(initial.get(field) == current.get(field) for field in fields)


def stress_variants(
    *,
    excavator_only_enabled: bool,
    front_teeth_only_enabled: bool,
) -> tuple[CaptureVariant, ...]:
    if not excavator_only_enabled or not front_teeth_only_enabled:
        raise ValueError(
            "Visibility stress requires both excavator_only_capture and "
            "front_teeth_only_capture"
        )
    return (
        CaptureVariant.EXCAVATOR_ONLY,
        CaptureVariant.FRONT_TEETH_ONLY,
        CaptureVariant.FULL_SCENE,
    )


def main(argv: list[str] | None = None) -> int:
    cli = parse_args(argv)
    capture = CaptureLaunchConfig.load(cli.config)
    profile = RenderProfile.load(capture.render_profile).with_capture_overrides(
        rt_subframes=capture.rt_subframes,
        warmup_render_frames=capture.warmup_render_frames,
    )
    joint_profile = JointControlProfile.load(capture.joint_profile)
    timing = validate_args(capture, profile, joint_profile)
    if cli.cycles > capture.frames:
        raise ValueError(
            f"Stress cycles ({cli.cycles}) exceed configured capture frames "
            f"({capture.frames})"
        )
    variants = stress_variants(
        excavator_only_enabled=capture.excavator_only_capture.enabled,
        front_teeth_only_enabled=capture.front_teeth_only_capture.enabled,
    )
    excavator_config = IsolatedRenderConfig.load(
        capture.excavator_only_capture.render_prim_paths_config
    )
    front_config = IsolatedRenderConfig.load(
        capture.front_teeth_only_capture.render_prim_paths_config
    )

    output_path = Path(cli.output).expanduser().resolve()
    if output_path.exists() and any(output_path.iterdir()):
        raise FileExistsError(f"Diagnostic output folder is not empty: {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / "visibility_stress_report.json"
    trace_path = output_path / "visibility_stress_trace.jsonl"
    initial_source = file_record(capture.usd)
    report: dict[str, Any] = {
        "status": "running",
        "started_at_utc": utc_now(),
        "config": str(Path(cli.config).resolve()),
        "source_stage_initial": initial_source,
        "cycles_requested": cli.cycles,
        "transitions_requested": cli.cycles * len(variants),
        "sequence": [variant.value for variant in variants],
        "rt_subframes": cli.rt_subframes,
        "boundary_start_generation": cli.boundary_start_generation,
        "boundary_rt_subframes": cli.boundary_rt_subframes,
        "dataset_frames_published": 0,
        "runtime_semantic_id_enabled": False,
    }
    write_json_atomic(report_path, report)

    simulation_app = None
    camera_scheduler = None
    world_scheduler = None
    motion_scheduler = None
    variant_controller = None
    failure: Exception | None = None
    transitions_completed = 0
    retry_reapplications = 0
    trace_stream = None

    try:
        from isaacsim import SimulationApp

        simulation_app = SimulationApp(
            launch_config=profile.launch_config(capture.headless)
        )

        import carb.settings
        import omni.usd

        from articulation_stage_validator import validate_articulation_stage
        from excavator_joint_motion import ExcavatorJointMotion
        from scene_visibility_controller import SceneVariantController
        from semantic_capture_custom import SemanticCameraScheduler
        from world_scheduler import WorldScheduler

        print(f"[visibility-stress] Loading immutable source Stage: {capture.usd}")
        if not omni.usd.get_context().open_stage(capture.usd):
            raise RuntimeError(f"Failed to open USD stage: {capture.usd}")
        stage = wait_for_opened_stage(simulation_app, capture.usd)
        simulation_app.reset_render_settings()
        report["render"] = RenderProfileManager(
            carb.settings.get_settings()
        ).apply_and_snapshot(profile)

        preflight = StagePreflight(
            stage=stage,
            source_stage=capture.usd,
            mapping_path=capture.mapping,
            camera_path=capture.camera_prim_path,
            joint_specs=(),
        ).run()
        preflight.raise_if_unusable()
        preflight.raise_if_blocking(strict=capture.strict_stage)

        articulation_report = validate_articulation_stage(stage, joint_profile)
        articulation_report.require_valid()
        variant_controller = SceneVariantController(
            stage=stage,
            variant_prim_paths={
                CaptureVariant.EXCAVATOR_ONLY: excavator_config.render_prim_paths,
                CaptureVariant.FRONT_TEETH_ONLY: front_config.render_prim_paths,
            },
            protected_prim_paths=(capture.camera_prim_path,),
            layer_name="semantic_visibility_stress.usda",
            stage_update_callback=simulation_app.update,
        )
        report["persistent_usd_protection"] = variant_controller.protection_report()

        maximum_data_step = timing.data_step_for_frame(cli.cycles - 1)
        run_duration = (
            capture.pre_roll_steps
            + maximum_data_step
            + capture.articulation_ready_timeout_steps
            + 2
        ) / float(capture.physics_hz) + 1.0
        world_scheduler = WorldScheduler(
            simulation_app=simulation_app,
            stage=stage,
            physics_hz=capture.physics_hz,
            maximum_duration_seconds=run_duration,
        )
        world_scheduler.initialize()
        motion_scheduler = ExcavatorJointMotion(
            stage=stage,
            trajectory_path=Path(capture.trajectory).resolve(),
            joint_profile=joint_profile,
            stage_report=articulation_report,
            playback_mode=capture.trajectory_mode,
            interpolation=capture.interpolation,
            trajectory_metadata=joint_profile.load_and_validate_trajectory_metadata(
                capture.trajectory
            ),
        )
        motion_scheduler.bind()
        world_scheduler.start()
        bootstrap_steps = world_scheduler.bootstrap_until(
            predicate=lambda: motion_scheduler.ready,
            max_steps=capture.articulation_ready_timeout_steps,
            description="Articulation physics tensor",
        )
        motion_scheduler.initialize_runtime()
        world_scheduler.advance_exact_steps(
            1,
            before_step_callback=lambda _time: motion_scheduler.apply_initial_positions(),
            after_step_callback=lambda _time: motion_scheduler.after_physics_step(0.0),
        )
        if capture.pre_roll_steps:
            world_scheduler.advance_exact_steps(
                capture.pre_roll_steps,
                before_step_callback=lambda _time: motion_scheduler.before_physics_step(0.0),
                after_step_callback=lambda _time: motion_scheduler.after_physics_step(0.0),
            )
        world_scheduler.begin_data_timeline()
        frozen_world = world_scheduler.freeze_for_capture()
        report["bootstrap_steps"] = bootstrap_steps

        camera_scheduler = SemanticCameraScheduler(
            simulation_app=simulation_app,
            stage=stage,
            camera_path=capture.camera_prim_path,
            output_path=output_path,
            mapping_path=Path(capture.mapping).resolve(),
            width=capture.width,
            height=capture.height,
            rt_subframes=cli.rt_subframes,
            save_runtime_ids=False,
            strict_mapping=capture.strict_mapping,
            output_folders=capture.image_output_folders,
            transparent_isolated_background=True,
            save_front_teeth_only_rgb=False,
            variant_validation=capture.variant_validation,
            overwrite_output=False,
        )
        camera_scheduler.initialize()
        camera_scheduler.warmup(profile.warmup_render_frames)
        world_scheduler.assert_still_frozen(frozen_world)
        camera_scheduler.attach_writer()
        report["camera_initial_state"] = camera_scheduler.get_state()
        write_json_atomic(report_path, report)

        probe_sequence = count()
        trace_stream = trace_path.open("w", encoding="utf-8")
        for cycle_id in range(cli.cycles):
            variant_controller.assert_state(CaptureVariant.FULL_SCENE)
            target_step = timing.data_step_for_frame(cycle_id)
            steps_to_advance = target_step - world_scheduler.dataset_step
            if steps_to_advance < 0:
                raise RuntimeError(
                    f"Stress schedule moved backwards at cycle {cycle_id}: "
                    f"target={target_step}, current={world_scheduler.dataset_step}"
                )
            if steps_to_advance:
                world_scheduler.resume_after_capture()
                world_scheduler.advance_exact_steps(
                    steps_to_advance,
                    before_step_callback=motion_scheduler.before_physics_step,
                    after_step_callback=motion_scheduler.after_physics_step,
                )
            frozen_world = world_scheduler.freeze_for_capture()
            expected_time = timing.dataset_time_for_frame(cycle_id)
            camera_state = camera_scheduler.get_state()
            base_context = CaptureContext(
                frame_id=cycle_id,
                dataset_time=expected_time,
                timeline_time=frozen_world.timeline_time,
                physics_step=frozen_world.physics_step,
                camera_path=camera_scheduler.camera_path,
                camera_world_transform=tuple(camera_state["world_transform"]),
                motion_state=motion_scheduler.get_state(expected_time),
                variant=CaptureVariant.FULL_SCENE,
                operation=CaptureOperation.CAPTURE,
                visibility_generation=variant_controller.visibility_generation,
            )
            cycle_receipts: list[dict[str, Any]] = []
            for target_variant in variants:
                next_generation = variant_controller.visibility_generation + 1
                subframes = (
                    cli.boundary_rt_subframes
                    if next_generation >= cli.boundary_start_generation
                    else cli.rt_subframes
                )
                _transition, probes = settle_variant(
                    camera_scheduler=camera_scheduler,
                    world_scheduler=world_scheduler,
                    frozen_world=frozen_world,
                    variant_controller=variant_controller,
                    base_context=base_context,
                    target_variant=target_variant,
                    settle_render_count=1,
                    settle_rt_subframes=subframes,
                    maximum_settle_attempts=(
                        capture.variant_transition.maximum_settle_attempts
                    ),
                    probe_sequence=probe_sequence,
                )
                transitions_completed += 1
                retry_reapplications += max(0, probes[-1].attempt - 1)
                cycle_receipts.extend(probe.to_dict() for probe in probes)
                world_scheduler.assert_still_frozen(frozen_world)
                assert_camera_matches_context(camera_scheduler, base_context)

            trace_stream.write(
                json.dumps(
                    {
                        "cycle": cycle_id,
                        "dataset_time": expected_time,
                        "end_visibility_generation": (
                            variant_controller.visibility_generation
                        ),
                        "probes": cycle_receipts,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            trace_stream.flush()
            if (cycle_id + 1) % cli.progress_every == 0 or cycle_id + 1 == cli.cycles:
                print(
                    f"[visibility-stress] cycles={cycle_id + 1}/{cli.cycles}, "
                    f"transitions={transitions_completed}, "
                    f"generation={variant_controller.visibility_generation}, "
                    f"retry_reapplications={retry_reapplications}"
                )

        camera_scheduler.wait_until_complete()
        variant_controller.assert_state(CaptureVariant.FULL_SCENE)
        variant_controller.assert_persistent_layers_pristine()
        report["end_variant"] = variant_controller.current_variant.value
        report["writer"] = camera_scheduler.statistics()
        report["last_visibility_generation"] = variant_controller.visibility_generation
    except Exception as exc:
        failure = exc
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        if trace_stream is not None:
            trace_stream.close()
        if variant_controller is not None:
            try:
                variant_controller.close()
            except Exception as exc:
                if failure is None:
                    failure = exc
                report["visibility_cleanup_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
        current_source = file_record(capture.usd)
        source_unchanged = source_records_equal(initial_source, current_source)
        report["source_stage_integrity"] = {
            "unchanged": source_unchanged,
            "initial": initial_source,
            "current": current_source,
        }
        if not source_unchanged and failure is None:
            failure = RuntimeError("Persistent source USD changed during stress test")
            report["error"] = {
                "type": type(failure).__name__,
                "message": str(failure),
            }
        report["transitions_completed"] = transitions_completed
        report["retry_reapplications"] = retry_reapplications
        report["completed_at_utc"] = utc_now()
        report["status"] = "failed" if failure is not None else "complete"
        write_json_atomic(report_path, report)

        if world_scheduler is not None:
            try:
                world_scheduler.stop()
            except Exception:
                pass
        if camera_scheduler is not None:
            try:
                camera_scheduler.close()
            except Exception:
                pass
        if motion_scheduler is not None:
            try:
                motion_scheduler.shutdown()
            except Exception:
                pass
        if simulation_app is not None:
            simulation_app.close()

    if failure is not None:
        print(f"[visibility-stress] FAILED: {failure}", file=sys.stderr)
        return 1
    print(
        f"[visibility-stress] PASS: {transitions_completed} transitions in one process; "
        f"source USD unchanged={report['source_stage_integrity']['unchanged']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
