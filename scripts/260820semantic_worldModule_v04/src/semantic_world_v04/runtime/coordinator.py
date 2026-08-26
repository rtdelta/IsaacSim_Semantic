"""Variant-major headless capture coordination."""

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from semantic_world_v04.compiler.job_compiler import utc_now
from semantic_world_v04.core.models import JobSpec, SegmentSpec, VariantDefinition
from semantic_world_v04.core.sensor_models import CaptureBatchKey, CaptureContext
from semantic_world_v04.core.progress import expected_capture_keys
from semantic_world_v04.core.serde import pretty_json
from semantic_world_v04.output import (
    AtomicCaptureBatchWriter,
    AtomicFrameWriter,
    BatchLedger,
    FrameLedger,
    StatusStore,
)
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.output.validators import validate_encoded_artifact
from semantic_world_v04.plugins import build_default_registry
from semantic_world_v04.stage.omni_adapter import (
    SessionSensorOverrideController,
    SessionVisibilityController,
    build_stage_index,
)

from .bootstrap import SimulationRuntime
from .capture_clock import SensorCaptureClock
from .encoding import SemanticPalette
from .motion import create_motion_controller
from .world import TimelineWorld


class CaptureCancelled(Exception):
    pass


class CaptureCoordinator:
    def __init__(
        self,
        *,
        job_spec: JobSpec,
        runtime: SimulationRuntime,
        output_dir: Any,
        status_store: Optional[StatusStore],
        cancelled: Callable[[], bool],
        segment_spec: Optional[SegmentSpec] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        from pathlib import Path

        self.job_spec = job_spec
        self.runtime = runtime
        self.output_dir = Path(output_dir)
        self.status_store = status_store
        self.cancelled = cancelled
        self.segment_spec = segment_spec
        self.progress_callback = progress_callback
        self.registry = build_default_registry()
        self.ledger = FrameLedger(self.output_dir / "ledger.jsonl")
        self.writer = AtomicFrameWriter(
            self.output_dir,
            self.ledger,
            retain_staging_on_failure=job_spec.project.output.retain_staging_on_failure,
        )
        self.batch_ledger = BatchLedger(self.output_dir / "batch_ledger.jsonl")
        self.batch_writer = AtomicCaptureBatchWriter(
            self.output_dir,
            self.ledger,
            self.batch_ledger,
            retain_staging_on_failure=job_spec.project.output.retain_staging_on_failure,
        )
        self.palette = SemanticPalette()
        self.drivers: Dict[str, Any] = {}
        self.visibility = None
        self.sensor_overrides = None
        self.motion = None
        self.world = None
        self.capture_clock = SensorCaptureClock()
        self._segment_committed = 0

    def run(self) -> None:
        stage = self.runtime.stage
        app = self.runtime.app
        if stage is None or app is None:
            raise RuntimeError("Simulation Runtime is not ready")
        project = self.job_spec.project
        stage_index = build_stage_index(stage)
        issues = [
            issue
            for issue in self.registry_validation(stage_index)
            if issue.severity == "error"
        ]
        if issues:
            raise ValueError(
                "Stage validation failed: " + "; ".join(str(issue) for issue in issues)
            )

        selected_variants = (
            None if self.segment_spec is None else set(self.segment_spec.variant_ids)
        )
        variants = [
            variant
            for variant in project.variants
            if variant.enabled
            and (selected_variants is None or variant.variant_id in selected_variants)
        ]
        requested_by_sensor = self._requested_modalities(variants)
        self.sensor_overrides = SessionSensorOverrideController(stage)
        for sensor in project.sensors:
            modalities = requested_by_sensor.get(sensor.sensor_id, set())
            if not sensor.enabled or not modalities:
                continue
            sensor_plugin = self.registry.sensor(sensor.plugin)
            self.sensor_overrides.apply(sensor, sensor_plugin)
            driver = sensor_plugin.create_runtime_driver(
                sensor,
                resolution=(
                    project.render.resolution_width,
                    project.render.resolution_height,
                ),
                modalities=modalities,
            )
            driver.initialize(stage)
            self.drivers[sensor.sensor_id] = driver

        if not self.drivers:
            raise ValueError("no enabled sensor has requested modalities")
        self.capture_clock.configure(self.drivers.values())
        self._write_effective_sensor_snapshot()
        self.visibility = SessionVisibilityController(stage)
        self.motion = create_motion_controller(
            project.motion, self.job_spec.source_project_path
        )
        self.world = TimelineWorld(app, project.capture.physics_hz)
        self.world.initialize(self.motion)

        start_frame, _ = self._capture_range()
        self._segment_committed = sum(
            1
            for frame_index, sensor_id, variant_id in expected_capture_keys(
                project, *self._capture_range()
            )
            if self.writer.is_committed(frame_index, sensor_id, variant_id)
        )
        start_step = self._target_step(start_frame)
        first_variant = True
        for variant in variants:
            self._check_cancelled()
            plan = self.registry.variant(variant.strategy).visibility_plan(
                variant,
                stage_index,
                [sensor.sensor.prim_path for sensor in self.drivers.values()],
            )
            self.visibility.apply(plan)
            self._position_variant_start(start_step, first_variant)
            first_variant = False
            self.runtime.reset_render_history()
            self.runtime.warmup(project.render.warmup_frames)
            self._capture_variant(variant)

    def _position_variant_start(self, start_step: int, first_variant: bool) -> None:
        assert self.world is not None and self.motion is not None
        force_replay = bool(
            self.segment_spec is not None
            and self.segment_spec.motion_positioning == "replay_from_zero"
        )
        can_seek = bool(
            getattr(self.motion, "supports_absolute_seek", False)
        ) and not force_replay
        if first_variant:
            if start_step > 0:
                if can_seek:
                    self.world.seek_to_absolute_step(start_step, self.motion)
                else:
                    self.world.advance_to(start_step, self.motion)
            return
        if can_seek:
            self.world.seek_to_absolute_step(start_step, self.motion)
            return

        # Non-seek motion must replay from a clean time-zero controller for
        # each variant. This is slower but preserves incremental/dynamic state.
        self.world.close()
        self.motion.close()
        self.motion = create_motion_controller(
            self.job_spec.project.motion, self.job_spec.source_project_path
        )
        self.world = TimelineWorld(
            self.runtime.app, self.job_spec.project.capture.physics_hz
        )
        self.world.initialize(self.motion)
        if start_step > 0:
            self.world.advance_to(start_step, self.motion)

    def close(self) -> None:
        self.capture_clock.close()
        for driver in reversed(list(self.drivers.values())):
            driver.close()
        self.drivers.clear()
        if self.visibility is not None:
            self.visibility.clear()
            self.visibility = None
        if self.sensor_overrides is not None:
            self.sensor_overrides.clear()
            self.sensor_overrides = None
        if self.motion is not None:
            self.motion.close()
            self.motion = None
        if self.world is not None:
            self.world.close()
            self.world = None

    def registry_validation(self, stage_index: Any):
        from semantic_world_v04.compiler import ProjectValidator

        return ProjectValidator(self.registry).validate(
            self.job_spec.project, stage_index
        )

    def _capture_variant(self, variant: VariantDefinition) -> None:
        project = self.job_spec.project
        assert self.world is not None
        start_frame, frame_count = self._capture_range()
        for offset in range(frame_count):
            self._check_cancelled()
            frame_index = start_frame + offset
            target_step = self._target_step(frame_index)
            self.world.advance_to(target_step, self.motion)
            batches: Dict[str, List[Any]] = {}
            for sensor_id, driver in self.drivers.items():
                requested = variant.modalities_by_sensor.get(sensor_id, [])
                if not requested:
                    continue
                sync_group_id = self._sync_group_id(sensor_id)
                key = CaptureBatchKey(
                    frame_index=frame_index,
                    variant_id=variant.variant_id,
                    sync_group_id=sync_group_id,
                )
                if self.batch_writer.is_committed(key):
                    continue
                frame_committed = self.writer.is_committed(
                    frame_index, sensor_id, variant.variant_id
                )
                batches.setdefault(sync_group_id, []).append(
                    (driver, list(requested), frame_committed)
                )
            if not batches:
                continue
            triggered = set()
            for members in batches.values():
                for driver, _, frame_committed in members:
                    if frame_committed:
                        continue
                    trigger_key = driver.capture_trigger_key
                    if trigger_key in triggered:
                        continue
                    driver.trigger_capture(project.render.rt_subframes)
                    triggered.add(trigger_key)
            capture_timestamp = utc_now()
            for sync_group_id, batch_members in batches.items():
                members: Dict[str, Dict[str, Any]] = {}
                newly_committed = 0
                for driver, requested, frame_committed in batch_members:
                    self._check_cancelled()
                    artifacts = {}
                    if not frame_committed:
                        capture_context = CaptureContext(
                            job_id=self.job_spec.job_id,
                            segment_id=(
                                self.segment_spec.segment_id
                                if self.segment_spec is not None
                                else "unsegmented"
                            ),
                            frame_index=frame_index,
                            simulation_step=target_step,
                            simulation_time_seconds=(
                                target_step / float(project.capture.physics_hz)
                            ),
                            capture_timestamp=capture_timestamp,
                            variant_id=variant.variant_id,
                            sync_group_id=sync_group_id,
                            renderer=project.render.renderer,
                            meters_per_unit=float(
                                getattr(driver, "meters_per_unit", 1.0)
                            ),
                        )
                        read_sample = getattr(driver, "read_sample", None)
                        sample = None
                        if callable(read_sample):
                            sample = read_sample(requested, capture_context)
                            payload = sample.modality_payloads
                        else:
                            payload = driver.read(requested)
                        artifacts = self._artifacts(
                            frame_index=frame_index,
                            variant=variant,
                            driver=driver,
                            requested=requested,
                            payload=payload,
                            capture_timestamp=capture_timestamp,
                            sync_group_id=sync_group_id,
                            sample=sample,
                        )
                        newly_committed += 1
                    members[driver.sensor_id] = {
                        "requested_modalities": requested,
                        "artifacts": artifacts,
                    }
                self.batch_writer.commit(
                    key=CaptureBatchKey(
                        frame_index=frame_index,
                        variant_id=variant.variant_id,
                        sync_group_id=sync_group_id,
                    ),
                    simulation_time=target_step / float(project.capture.physics_hz),
                    members=members,
                )
                self._segment_committed += newly_committed
                self._write_palette()
                self._update_progress(
                    f"Committed frame {frame_index}, sync group {sync_group_id}, "
                    f"variant {variant.variant_id}"
                )
            self.world.restore_after_capture()

    def _artifacts(
        self,
        *,
        frame_index: int,
        variant: VariantDefinition,
        driver: Any,
        requested: Sequence[str],
        payload: Mapping[str, Any],
        capture_timestamp: str,
        sync_group_id: str,
        sample: Any = None,
    ) -> Dict[str, Any]:
        stem = (
            f"sensors/{driver.sensor_id}/{variant.variant_id}"
        )
        filename = f"{frame_index:06d}"
        artifacts: Dict[str, Any] = {}
        runtime_metadata: Dict[str, Any] = {}
        modality_by_id = {
            modality.modality_id: modality
            for modality in self.job_spec.project.modalities
            if modality.enabled
        }
        context = {"semantic_palette": self.palette}
        for modality_id in requested:
            definition = modality_by_id[modality_id]
            plugin = self.registry.modality(definition.plugin)
            context["modality_options"] = dict(definition.options)
            encoded, metadata = plugin.encode_runtime(payload, context)
            sensor_resolution = getattr(driver, "output_resolution", None)
            expected_resolution = (
                None
                if sensor_resolution is None
                else (int(sensor_resolution[0]), int(sensor_resolution[1]))
            )
            validate_encoded_artifact(
                modality_id,
                bytes(encoded),
                expected_resolution=expected_resolution,
            )
            artifacts[
                f"{stem}/{modality_id}/{filename}{plugin.output_extension}"
            ] = encoded
            runtime_metadata.update(metadata)
        metadata = {
            "schema_version": 1,
            "job_id": self.job_spec.job_id,
            "frame_index": frame_index,
            "simulation_time": self._target_step(frame_index)
            / float(self.job_spec.project.capture.physics_hz),
            "sensor_id": driver.sensor_id,
            "sensor_plugin": driver.sensor.plugin,
            "sensor_plugin_version": driver.sensor.plugin_version,
            "sensor_backend": driver.sensor.backend,
            "sensor_prim_path": driver.sensor.prim_path,
            "capture_timestamp": capture_timestamp,
            "sync_group_id": sync_group_id,
            "stage_sensor_parameters": dict(driver.sensor.stage_parameters),
            "configured_sensor_parameters": dict(driver.sensor.parameters),
            "parameter_sources": dict(driver.sensor.parameter_sources),
            "effective_sensor_parameters": dict(
                driver.effective_parameters_snapshot
            ),
            "variant_id": variant.variant_id,
            "requested_modalities": list(requested),
            **runtime_metadata,
        }
        if sample is not None:
            metadata["calibration"] = sample.calibration_snapshot.to_dict()
            metadata["payloads"] = {
                name: value.descriptor()
                for name, value in sample.modality_payloads.items()
            }
            metadata["sequence_metadata"] = dict(sample.sequence_metadata)
            metadata["sensor_diagnostics"] = dict(sample.diagnostics)
        artifacts[f"{stem}/metadata/{filename}.json"] = pretty_json(metadata)
        return artifacts

    def _write_effective_sensor_snapshot(self) -> None:
        sensors = {}
        for sensor_id, driver in self.drivers.items():
            sensor = driver.sensor
            sensors[sensor_id] = {
                "plugin": sensor.plugin,
                "plugin_version": sensor.plugin_version,
                "backend": sensor.backend,
                "sync_group_id": self._sync_group_id(sensor_id),
                "prim_path": sensor.prim_path,
                "stage_parameters": dict(sensor.stage_parameters),
                "configured_parameters": dict(sensor.parameters),
                "parameter_sources": dict(sensor.parameter_sources),
                "effective_parameters": dict(
                    driver.effective_parameters_snapshot
                ),
            }
        atomic_write_json(
            self.output_dir / "sensor_effective_parameters.json",
            {"schema_version": 1, "sensors": sensors},
        )
        for sensor_id, driver in self.drivers.items():
            snapshot_provider = getattr(driver, "calibration_snapshot", None)
            if callable(snapshot_provider):
                atomic_write_json(
                    self.output_dir / "calibrations" / f"{sensor_id}.json",
                    {
                        "schema_version": 1,
                        "calibration": snapshot_provider().to_dict(),
                    },
                )
        for rig in self.job_spec.project.rigs:
            if not rig.enabled:
                continue
            atomic_write_json(
                self.output_dir / "calibrations" / "rigs" / f"{rig.rig_id}.json",
                {
                    "schema_version": 1,
                    "rig": rig.to_dict(),
                    "sensor_calibrations": {
                        sensor_id: self.drivers[sensor_id]
                        .calibration_snapshot()
                        .to_dict()
                        for sensor_id in rig.sensor_ids
                        if sensor_id in self.drivers
                        and callable(
                            getattr(self.drivers[sensor_id], "calibration_snapshot", None)
                        )
                    },
                },
            )

    def _sync_group_id(self, sensor_id: str) -> str:
        project = self.job_spec.project
        matches = [
            rig.rig_id
            for rig in project.rigs
            if rig.enabled and sensor_id in rig.sensor_ids
        ]
        if len(matches) > 1:
            raise ValueError(f"sensor {sensor_id} belongs to multiple enabled rigs")
        if matches:
            return matches[0]
        sensor = next(item for item in project.sensors if item.sensor_id == sensor_id)
        return sensor.sync_group_id or sensor.sensor_id

    def _requested_modalities(
        self, variants: Sequence[VariantDefinition]
    ) -> Dict[str, set]:
        result: Dict[str, set] = {}
        for variant in variants:
            for sensor_id, modalities in variant.modalities_by_sensor.items():
                result.setdefault(sensor_id, set()).update(modalities)
        return result

    def _target_step(self, frame_index: int) -> int:
        capture = self.job_spec.project.capture
        steps = capture.physics_hz // capture.capture_fps
        return (
            frame_index * steps
            if capture.capture_initial_frame
            else (frame_index + 1) * steps
        )

    def _write_palette(self) -> None:
        atomic_write_json(
            self.output_dir / "semantic_mapping.json",
            self.palette.mapping_document(),
        )

    def _update_progress(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message, self._segment_committed)
            return
        if self.status_store is None:
            return
        status = self.status_store.read()
        status.state = "running"
        status.frame_current = len(list(self.ledger.entries()))
        status.updated_at_utc = utc_now()
        status.last_heartbeat_utc = status.updated_at_utc
        status.message = message
        self.status_store.write(status)

    def _capture_range(self):
        if self.segment_spec is not None:
            return self.segment_spec.start_frame, self.segment_spec.frame_count
        capture = self.job_spec.project.capture
        return capture.start_frame, capture.frame_count

    def _check_cancelled(self) -> None:
        if self.cancelled():
            raise CaptureCancelled("capture cancellation requested")
