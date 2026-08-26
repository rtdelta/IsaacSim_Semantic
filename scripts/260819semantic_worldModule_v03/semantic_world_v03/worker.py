"""Short-lived Isaac Sim worker for one restartable capture segment."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any

from .config import RunConfig, load_run_config
from .coordinator import CaptureCoordinator
from .heartbeat import HeartbeatWriter
from .ledger import CommitLedger
from .registry import build_default_registry
from .rendering import (
    IsaacRenderBackend,
    RenderGroupManager,
    resolve_profiles,
)
from .semantic_mapping import SemanticMapping
from .sensors.base import SensorRuntimeContext
from .sinks import FilesystemSink
from .timing import CaptureTimeline
from .variants import VariantController, reset_render_history
from .world import WorldController, open_stage_and_wait


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one semantic-world v03 worker segment")
    parser.add_argument("--config", required=True)
    parser.add_argument("--segment-id", required=True)
    parser.add_argument("--start-frame", required=True, type=int)
    parser.add_argument("--end-frame", required=True, type=int)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--heartbeat", required=True)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _apply_render_settings(
    profiles: dict[str, Any], group_settings: list[dict[str, Any]]
) -> dict[str, Any]:
    import carb.settings

    interface = carb.settings.get_settings()
    requested: dict[str, Any] = {}
    for profile in profiles.values():
        for key, value in profile.settings.items():
            interface.set(key, value)
            requested[key] = value
    for values in group_settings:
        for key, value in values.items():
            if key in requested and requested[key] != value:
                raise RuntimeError(f"Render group settings disagree on global setting {key}")
            interface.set(key, value)
            requested[key] = value
    effective = {key: interface.get(key) for key in requested}
    mismatch = {
        key: {"requested": requested[key], "effective": effective[key]}
        for key in requested
        if requested[key] != effective[key]
    }
    if mismatch:
        raise RuntimeError(f"Render settings failed read-back: {mismatch}")
    return {"requested": requested, "effective": effective}


def _run(args: argparse.Namespace, config: RunConfig, heartbeat: HeartbeatWriter) -> None:
    profiles = resolve_profiles(config.render_groups.values())
    primary_profile = next(iter(profiles.values()), None)
    launch = primary_profile.launch_config(headless=args.headless) if primary_profile else {
        "headless": args.headless,
        "sync_loads": True,
    }
    multi_gpu_values = {group.multi_gpu for group in config.render_groups.values()}
    if len(multi_gpu_values) > 1:
        raise ValueError("All render groups in one worker must agree on multi_gpu")
    launch["multi_gpu"] = next(iter(multi_gpu_values))
    heartbeat.touch("starting", segment_id=args.segment_id, launch=launch)
    from isaacsim import SimulationApp

    simulation_app = SimulationApp(launch)
    drivers: dict[str, Any] = {}
    world: WorldController | None = None
    motion = None
    failure: BaseException | None = None
    try:
        heartbeat.touch("loading_stage", segment_id=args.segment_id)
        stage = open_stage_and_wait(simulation_app, config.scene.usd)
        # A newly opened Stage can restore authored render settings. Re-apply
        # the launch renderer first, then the strict profile, and only then
        # record the effective settings used for capture.
        simulation_app.reset_render_settings()
        render_snapshot = _apply_render_settings(
            profiles, [group.settings for group in config.render_groups.values()]
        )
        stage.SetEditTarget(stage.GetSessionLayer())
        backend = IsaacRenderBackend(simulation_app)
        ledger = CommitLedger(config.output, run_id=config.run_id, fingerprint=config.fingerprint)
        registry = build_default_registry(config.driver_plugins)
        preflight: dict[str, Any] = {}
        context = SensorRuntimeContext(
            simulation_app=simulation_app,
            stage=stage,
            render_backend=backend,
            output_root=Path(config.output),
            services={},
        )
        heartbeat.touch(
            "initializing_sensors", segment_id=args.segment_id, step="preflight"
        )
        for spec in config.enabled_sensors:
            driver = registry.create(spec)
            report = driver.preflight(stage)
            report.require_usable()
            preflight[spec.sensor_id] = report.to_dict()
            drivers[spec.sensor_id] = driver
        timeline = CaptureTimeline(config)
        heartbeat.touch(
            "initializing_sensors", segment_id=args.segment_id, step="scene_variants"
        )
        variants = VariantController(
            stage,
            config.capture.variants,
            protected_paths=(
                sensor.source.resolved_prim_path for sensor in config.enabled_sensors
            ),
        )
        if config.capture.variant_execution == "variant_major":
            variants.apply(args.variant)
            reset_render_history()
        maximum_step = timeline.physics_step_for_frame(config.capture.frames - 1)
        heartbeat.touch(
            "initializing_sensors", segment_id=args.segment_id, step="world"
        )
        world = WorldController(simulation_app, stage, config.scene)
        world.initialize(maximum_step)
        if config.scene.motion is not None:
            heartbeat.touch(
                "initializing_sensors", segment_id=args.segment_id, step="motion"
            )
            simulation_app.update()
            module_name, class_name = config.scene.motion.driver.split(":", 1)
            motion_class = getattr(importlib.import_module(module_name), class_name)
            motion = motion_class(config.scene.motion, stage)
            motion.initialize()
        world.freeze()
        start_step = timeline.physics_step_for_frame(args.start_frame)
        if (
            start_step > 0
            and motion is not None
            and bool(getattr(motion, "supports_absolute_seek", False))
            and callable(getattr(motion, "seek", None))
        ):
            heartbeat.touch(
                "seeking",
                segment_id=args.segment_id,
                physics_step=start_step,
                target_start_frame=args.start_frame,
            )
            world.seek_to_absolute_step(start_step, motion.seek)
            # The paused propagation update above may have accumulated a
            # transient sample.  Sensor initialization and configured warmup
            # below now start a fresh PathTracing history at the sought pose.
            reset_render_history()
        elif motion is not None:
            motion.before_step(0.0)
        for sensor_id, driver in drivers.items():
            heartbeat.touch(
                "initializing_sensors",
                segment_id=args.segment_id,
                step="sensor_runtime",
                sensor_id=sensor_id,
            )
            driver.initialize(context)
        heartbeat.touch("warming", segment_id=args.segment_id)
        for group in config.render_groups.values():
            backend.update(group.warmup_frames)
        for driver in drivers.values():
            driver.warmup()
        world.resume()
        mapping = SemanticMapping.load(config.scene.mapping) if config.scene.mapping else None
        sink = FilesystemSink(mapping)
        groups = RenderGroupManager(backend, config.render_groups)
        coordinator = CaptureCoordinator(config, drivers, groups, sink, ledger, heartbeat)
        ledger.write_manifest(
            "worker_running",
            segment_id=args.segment_id,
            render_profiles={key: value.sha256 for key, value in profiles.items()},
            render_settings=render_snapshot,
            preflight=preflight,
        )

        last_replay_heartbeat = 0.0

        def report_replay(step: int) -> None:
            nonlocal last_replay_heartbeat
            now = time.monotonic()
            if now - last_replay_heartbeat >= config.runtime.heartbeat_seconds:
                heartbeat.touch(
                    "replaying", segment_id=args.segment_id, physics_step=step,
                    target_start_frame=args.start_frame,
                )
                last_replay_heartbeat = now

        if config.capture.variant_execution == "variant_major":
            for frame_id in range(args.start_frame, args.end_frame):
                target = timeline.physics_step_for_frame(frame_id)
                world.advance_to(
                    target,
                    report_replay,
                    getattr(motion, "before_step", None),
                    getattr(motion, "after_step", None),
                )
                snapshot = world.freeze()
                coordinator.capture_frame(args.variant, frame_id, snapshot)
                world.assert_frozen(snapshot)
                world.resume()
        else:
            for frame_id in range(args.start_frame, args.end_frame):
                target = timeline.physics_step_for_frame(frame_id)
                world.advance_to(
                    target,
                    report_replay,
                    getattr(motion, "before_step", None),
                    getattr(motion, "after_step", None),
                )
                snapshot = world.freeze()
                for variant in config.capture.variants:
                    variants.apply(variant.variant_id)
                    reset_render_history()
                    coordinator.capture_frame(variant.variant_id, frame_id, snapshot)
                    world.assert_frozen(snapshot)
                world.resume()
        heartbeat.touch("closing", segment_id=args.segment_id)
        ledger.write_manifest("worker_segment_complete", segment_id=args.segment_id)
    except BaseException as exc:
        failure = exc
        diagnostic = traceback.format_exc()
        heartbeat.touch(
            "failed_before_close",
            segment_id=args.segment_id,
            error=repr(exc),
            traceback=diagnostic,
        )
        print(diagnostic, flush=True)
        raise
    finally:
        if motion is not None:
            try:
                motion.close()
            except Exception:
                traceback.print_exc()
        if world is not None:
            world.close()
        for driver in reversed(tuple(drivers.values())):
            try:
                driver.close()
            except Exception:
                traceback.print_exc()
        # Isaac Sim's fast shutdown terminates the process. Preserve a failure
        # exit code so the external supervisor never mistakes an aborted worker
        # for a successful but incomplete segment.
        simulation_app.close(exit_code=1 if failure is not None else 0)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_run_config(args.config)
    heartbeat = HeartbeatWriter(
        args.heartbeat, run_id=config.run_id, worker_id=f"{args.segment_id}-{os.getpid()}"
    )
    try:
        _run(args, config, heartbeat)
    except BaseException as exc:
        heartbeat.touch(
            "failed", segment_id=args.segment_id, error=repr(exc), traceback=traceback.format_exc()
        )
        raise
    heartbeat.touch("complete", segment_id=args.segment_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
