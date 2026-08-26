"""Fail-fast validation shared by Studio, CLI, and Supervisor."""

import re
from typing import List, Optional, Set

from semantic_world_v04.core.errors import PluginError
from semantic_world_v04.core.models import ProjectDefinition, ValidationIssue
from semantic_world_v04.core.sensor_models import parameter_schema_issues
from semantic_world_v04.plugins.registry import PluginRegistry, build_default_registry
from semantic_world_v04.stage.index import StageIndex


class ProjectValidator:
    def __init__(self, registry: Optional[PluginRegistry] = None) -> None:
        self.registry = registry or build_default_registry()

    def validate(
        self, project: ProjectDefinition, stage_index: Optional[StageIndex] = None
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        issues.extend(self._unique_ids(project))
        issues.extend(self._capture(project))
        issues.extend(self._render(project))
        issues.extend(self._motion(project))
        issues.extend(self._semantics(project))
        issues.extend(self._execution(project))
        issues.extend(self._rigs(project))

        enabled_modalities = {
            modality.modality_id: modality
            for modality in project.modalities
            if modality.enabled
        }
        for index, modality in enumerate(project.modalities):
            try:
                plugin = self.registry.modality(modality.plugin)
            except PluginError as exc:
                issues.append(
                    ValidationIssue(
                        "modality.plugin",
                        str(exc),
                        f"modalities[{index}].plugin",
                    )
                )
                continue
            issues.extend(plugin.validate_options(modality.options))

        sensor_by_id = {sensor.sensor_id: sensor for sensor in project.sensors}
        for index, sensor in enumerate(project.sensors):
            if not sensor.enabled:
                continue
            try:
                plugin = self.registry.sensor(sensor.plugin)
            except PluginError as exc:
                issues.append(
                    ValidationIssue(
                        "sensor.plugin", str(exc), f"sensors[{index}].plugin"
                    )
                )
                continue
            issues.extend(plugin.validate(sensor, stage_index))
            manifest = self.registry.manifest("sensor", sensor.plugin)
            if sensor.plugin_version and sensor.plugin_version != manifest.plugin_version:
                issues.append(
                    ValidationIssue(
                        "sensor.plugin_version",
                        f"configured plugin version {sensor.plugin_version} differs "
                        f"from installed version {manifest.plugin_version}",
                        f"sensors[{index}].plugin_version",
                    )
                )
            capabilities_method = getattr(plugin, "capabilities", None)
            if callable(capabilities_method):
                capabilities = capabilities_method()
                if project.render.renderer not in capabilities.renderer_compatibility:
                    issues.append(
                        ValidationIssue(
                            "sensor.renderer_unsupported",
                            f"sensor plugin {sensor.plugin} does not support "
                            f"{project.render.renderer}",
                            f"sensors[{index}]",
                        )
                    )
            schema_method = getattr(plugin, "parameter_schema", None)
            if callable(schema_method):
                overrides = {
                    name: value
                    for name, value in sensor.parameters.items()
                    if sensor.parameter_sources.get(name, "override") == "override"
                }
                for message in parameter_schema_issues(
                    overrides,
                    schema_method(),
                    path=f"sensors[{index}].parameters",
                ):
                    issues.append(
                        ValidationIssue(
                            "sensor.parameter_schema",
                            message,
                            f"sensors[{index}].parameters",
                        )
                    )

        for index, variant in enumerate(project.variants):
            if not variant.enabled:
                continue
            try:
                strategy = self.registry.variant(variant.strategy)
            except PluginError as exc:
                issues.append(
                    ValidationIssue(
                        "variant.strategy", str(exc), f"variants[{index}].strategy"
                    )
                )
                continue
            issues.extend(strategy.validate(variant, stage_index))
            for sensor_id, modality_ids in variant.modalities_by_sensor.items():
                sensor = sensor_by_id.get(sensor_id)
                if sensor is None or not sensor.enabled:
                    issues.append(
                        ValidationIssue(
                            "variant.sensor_reference",
                            f"unknown or disabled sensor: {sensor_id}",
                            f"variants[{index}].modalities_by_sensor.{sensor_id}",
                        )
                    )
                    continue
                try:
                    supported: Set[str] = set(
                        self.registry.sensor(sensor.plugin).supported_modalities()
                    )
                except PluginError:
                    continue
                for modality_id in modality_ids:
                    if modality_id not in enabled_modalities:
                        issues.append(
                            ValidationIssue(
                                "variant.modality_reference",
                                f"unknown or disabled modality: {modality_id}",
                                (
                                    f"variants[{index}].modalities_by_sensor."
                                    f"{sensor_id}"
                                ),
                            )
                        )
                    elif modality_id not in supported:
                        issues.append(
                            ValidationIssue(
                                "variant.modality_unsupported",
                                (
                                    f"sensor plugin {sensor.plugin} does not support "
                                    f"{modality_id}"
                                ),
                                (
                                    f"variants[{index}].modalities_by_sensor."
                                    f"{sensor_id}"
                                ),
                            )
                        )
        if not any(sensor.enabled for sensor in project.sensors):
            issues.append(
                ValidationIssue(
                    "project.no_sensors",
                    "at least one sensor must be enabled",
                    "sensors",
                )
            )
        if not any(variant.enabled for variant in project.variants):
            issues.append(
                ValidationIssue(
                    "project.no_variants",
                    "at least one variant must be enabled",
                    "variants",
                )
            )
        return issues

    @staticmethod
    def _unique_ids(project: ProjectDefinition) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for name, values in (
            ("sensor", [item.sensor_id for item in project.sensors]),
            ("variant", [item.variant_id for item in project.variants]),
            ("modality", [item.modality_id for item in project.modalities]),
            ("rig", [item.rig_id for item in project.rigs]),
        ):
            seen = set()
            for index, item_id in enumerate(values):
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", item_id):
                    issues.append(
                        ValidationIssue(
                            f"{name}.unsafe_id",
                            (
                                f"{name} id must use only letters, numbers, "
                                "dot, underscore, or hyphen"
                            ),
                            f"{name}s[{index}]",
                        )
                    )
                if item_id in seen:
                    issues.append(
                        ValidationIssue(
                            f"{name}.duplicate_id",
                            f"duplicate {name} id: {item_id}",
                            f"{name}s[{index}]",
                        )
                    )
                seen.add(item_id)
        return issues

    @staticmethod
    def _rigs(project: ProjectDefinition) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        enabled_sensors = {
            sensor.sensor_id for sensor in project.sensors if sensor.enabled
        }
        owner = {}
        for index, rig in enumerate(project.rigs):
            if not rig.enabled:
                continue
            if not rig.sensor_ids:
                issues.append(
                    ValidationIssue(
                        "rig.empty",
                        "an enabled rig must contain at least one sensor",
                        f"rigs[{index}].sensor_ids",
                    )
                )
            if len(set(rig.sensor_ids)) != len(rig.sensor_ids):
                issues.append(
                    ValidationIssue(
                        "rig.duplicate_sensor",
                        "a rig must not list the same sensor more than once",
                        f"rigs[{index}].sensor_ids",
                    )
                )
            for sensor_id in rig.sensor_ids:
                if sensor_id not in enabled_sensors:
                    issues.append(
                        ValidationIssue(
                            "rig.sensor_reference",
                            f"unknown or disabled sensor: {sensor_id}",
                            f"rigs[{index}].sensor_ids",
                        )
                    )
                if sensor_id in owner:
                    issues.append(
                        ValidationIssue(
                            "rig.multiple_membership",
                            f"sensor {sensor_id} already belongs to rig {owner[sensor_id]}",
                            f"rigs[{index}].sensor_ids",
                        )
                    )
                owner[sensor_id] = rig.rig_id
            if rig.sync_policy != "same_simulation_step":
                issues.append(
                    ValidationIssue(
                        "rig.sync_policy",
                        "v04.3 currently supports same_simulation_step only",
                        f"rigs[{index}].sync_policy",
                    )
                )
            if rig.failure_policy != "all_or_retry":
                issues.append(
                    ValidationIssue(
                        "rig.failure_policy",
                        "v04.3 currently supports all_or_retry only",
                        f"rigs[{index}].failure_policy",
                    )
                )
            if (
                rig.reference_frame_prim_path is not None
                and not rig.reference_frame_prim_path.startswith("/")
            ):
                issues.append(
                    ValidationIssue(
                        "rig.reference_frame",
                        "reference_frame_prim_path must be an absolute USD Prim path",
                        f"rigs[{index}].reference_frame_prim_path",
                    )
                )
        for index, sensor in enumerate(project.sensors):
            if sensor.sensor_id in owner and sensor.sync_group_id not in {
                None,
                owner[sensor.sensor_id],
            }:
                issues.append(
                    ValidationIssue(
                        "rig.sync_group_conflict",
                        f"sensor sync_group_id conflicts with rig {owner[sensor.sensor_id]}",
                        f"sensors[{index}].sync_group_id",
                    )
                )
        return issues

    @staticmethod
    def _capture(project: ProjectDefinition) -> List[ValidationIssue]:
        capture = project.capture
        issues = []
        for field_name in ("physics_hz", "capture_fps", "frame_count", "segment_frames"):
            if getattr(capture, field_name) <= 0:
                issues.append(
                    ValidationIssue(
                        "capture.positive",
                        f"{field_name} must be greater than zero",
                        f"capture.{field_name}",
                    )
                )
        if capture.start_frame < 0:
            issues.append(
                ValidationIssue(
                    "capture.start_frame",
                    "start_frame must not be negative",
                    "capture.start_frame",
                )
            )
        if (
            capture.physics_hz > 0
            and capture.capture_fps > 0
            and capture.physics_hz % capture.capture_fps != 0
        ):
            issues.append(
                ValidationIssue(
                    "capture.non_integral_rate",
                    "physics_hz must be evenly divisible by capture_fps",
                    "capture.capture_fps",
                    hint="choose rates with an integer number of physics steps per capture",
                )
            )
        return issues

    @staticmethod
    def _render(project: ProjectDefinition) -> List[ValidationIssue]:
        render = project.render
        issues = []
        if render.renderer not in {"RayTracedLighting", "PathTracing"}:
            issues.append(
                ValidationIssue(
                    "render.renderer",
                    "renderer must be RayTracedLighting or PathTracing",
                    "render.renderer",
                )
            )
        for field_name in (
            "resolution_width",
            "resolution_height",
            "rt_subframes",
            "spp_per_frame",
            "total_spp",
            "max_bounces",
        ):
            if getattr(render, field_name) <= 0:
                issues.append(
                    ValidationIssue(
                        "render.positive",
                        f"{field_name} must be greater than zero",
                        f"render.{field_name}",
                    )
                )
        if render.warmup_frames < 0:
            issues.append(
                ValidationIssue(
                    "render.warmup_frames",
                    "warmup_frames must not be negative",
                    "render.warmup_frames",
                )
            )
        return issues

    @staticmethod
    def _motion(project: ProjectDefinition) -> List[ValidationIssue]:
        motion = project.motion
        issues: List[ValidationIssue] = []
        if motion.plugin not in {"none", "csv_articulation"}:
            return [
                ValidationIssue(
                    "motion.plugin",
                    "motion plugin must be none or csv_articulation",
                    "motion.plugin",
                )
            ]
        if motion.plugin == "none":
            if motion.source_path:
                issues.append(
                    ValidationIssue(
                        "motion.none_source",
                        "none motion must not define source_path",
                        "motion.source_path",
                    )
                )
            return issues
        if not motion.source_path:
            issues.append(
                ValidationIssue(
                    "motion.source_path",
                    "csv_articulation requires source_path",
                    "motion.source_path",
                )
            )
        options = motion.options
        prim_path = options.get("articulation_prim_path")
        if not isinstance(prim_path, str) or not prim_path.startswith("/"):
            issues.append(
                ValidationIssue(
                    "motion.articulation_prim_path",
                    "articulation_prim_path must be an absolute USD Prim path",
                    "motion.options.articulation_prim_path",
                )
            )
        joint_columns = options.get("joint_columns")
        if not isinstance(joint_columns, dict) or not joint_columns:
            issues.append(
                ValidationIssue(
                    "motion.joint_columns",
                    "joint_columns must be a non-empty DOF-to-CSV-column object",
                    "motion.options.joint_columns",
                )
            )
        elif any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in joint_columns.items()
        ):
            issues.append(
                ValidationIssue(
                    "motion.joint_columns",
                    "joint_columns keys and values must be non-empty strings",
                    "motion.options.joint_columns",
                )
            )
        if options.get("interpolation", "linear") not in {"linear", "hold"}:
            issues.append(
                ValidationIssue(
                    "motion.interpolation",
                    "interpolation must be linear or hold",
                    "motion.options.interpolation",
                )
            )
        if options.get("angle_units", "radians") not in {"radians", "degrees"}:
            issues.append(
                ValidationIssue(
                    "motion.angle_units",
                    "angle_units must be radians or degrees",
                    "motion.options.angle_units",
                )
            )
        return issues

    @staticmethod
    def _semantics(project: ProjectDefinition) -> List[ValidationIssue]:
        semantics = project.semantics
        issues: List[ValidationIssue] = []
        if not semantics.label_attribute.strip():
            issues.append(
                ValidationIssue(
                    "semantics.label_attribute",
                    "label_attribute must not be empty",
                    "semantics.label_attribute",
                )
            )
        if semantics.background_id < 0:
            issues.append(
                ValidationIssue(
                    "semantics.background_id",
                    "background_id must not be negative",
                    "semantics.background_id",
                )
            )
        return issues

    @staticmethod
    def _execution(project: ProjectDefinition) -> List[ValidationIssue]:
        execution = project.execution
        issues: List[ValidationIssue] = []
        if execution.segmentation_strategy not in {
            "auto",
            "single_worker",
            "replay_from_zero",
        }:
            issues.append(
                ValidationIssue(
                    "execution.segmentation_strategy",
                    "segmentation_strategy must be auto, single_worker, or replay_from_zero",
                    "execution.segmentation_strategy",
                )
            )
        for field_name in (
            "heartbeat_timeout_seconds",
            "no_progress_timeout_seconds",
            "segment_start_timeout_seconds",
            "graceful_stop_timeout_seconds",
            "telemetry_interval_seconds",
        ):
            if getattr(execution, field_name) <= 0:
                issues.append(
                    ValidationIssue(
                        "execution.positive",
                        f"{field_name} must be greater than zero",
                        f"execution.{field_name}",
                    )
                )
        if (
            execution.segmentation_strategy == "replay_from_zero"
            and project.motion.plugin == "none"
        ):
            issues.append(
                ValidationIssue(
                    "execution.unnecessary_replay",
                    "replay_from_zero is unnecessary when motion is none",
                    "execution.segmentation_strategy",
                    severity="warning",
                )
            )
        return issues
