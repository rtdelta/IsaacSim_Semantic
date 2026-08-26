"""RTX LiDAR plugin definition with version-isolated Runtime creation."""

from typing import Any, Dict, Optional, Sequence

from semantic_world_v04.core.models import SensorDefinition, ValidationIssue
from semantic_world_v04.core.sensor_models import (
    PluginManifest,
    SensorCapabilities,
    parameter_schema,
)
from semantic_world_v04.stage.index import PrimSummary, StageIndex

_LIDAR_TERMS = ("lidar", "rtxsensor", "laserscan")
_OVERRIDE_ALIASES = {
    "min_range": (
        "minRange",
        "minimumRange",
        "omni:sensor:minRange",
        "omni:sensor:Core:nearRangeM",
    ),
    "max_range": (
        "maxRange",
        "maximumRange",
        "omni:sensor:maxRange",
        "omni:sensor:Core:farRangeM",
    ),
    "rotation_frequency": (
        "rotationRate",
        "rotationFrequency",
        "omni:sensor:rotationRate",
        "omni:sensor:Core:scanRateBaseHz",
    ),
    "tick_rate": ("omni:sensor:tickRate",),
    "horizontal_fov": ("horizontalFov", "horizontalFOV"),
    "vertical_fov": ("verticalFov", "verticalFOV"),
}


def is_lidar_prim(prim: PrimSummary) -> bool:
    haystack = " ".join(
        [prim.type_name, *prim.applied_schemas, *prim.attributes.keys()]
    ).casefold()
    return any(term in haystack for term in _LIDAR_TERMS)


class RtxLidarPlugin:
    plugin_id = "rtx_lidar"

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id,
            plugin_kind="sensor",
            plugin_version="1.0.0",
            display_name="RTX LiDAR",
            definition_class=f"{__name__}:RtxLidarPlugin",
            runtime_requirements=("replicator", "rtx_sensor"),
            supported_modalities=tuple(self.supported_modalities()),
        )

    def capabilities(self) -> SensorCapabilities:
        return SensorCapabilities(
            payload_kinds=("point_cloud", "records"),
            time_model="scan_window",
            trigger_domain="replicator_orchestrator",
            synchronization_mode="rig_batch",
            renderer_compatibility=("RayTracedLighting", "PathTracing"),
            requires_continuous_history=True,
            calibration_model="rtx_lidar_scan_pattern",
            backend_requirements=(
                "isaacsim.sensors.rtx.nodes",
                "omni.replicator.core",
            ),
        )

    def parameter_schema(self) -> Dict[str, Any]:
        return parameter_schema(
            {
                "annotator": {"type": "string"},
                "tick_rate": {"type": "number", "minimum": 0.0},
                "min_range": {"type": "number", "minimum": 0.0},
                "max_range": {"type": "number", "minimum": 0.0},
                "rotation_frequency": {"type": "number", "minimum": 0.0},
                "horizontal_fov": {"type": "number", "minimum": 0.0},
                "vertical_fov": {"type": "number", "minimum": 0.0},
                "output_coordinate_frame": {
                    "type": "string",
                    "enum": ["sensor", "world"],
                },
                "scan_mode": {
                    "type": "string",
                    "enum": ["complete_scan", "current_frame"],
                },
                "points_unit": {
                    "type": "string",
                    "enum": ["meter", "stage_unit"],
                },
            }
        )

    def matches_prim(self, prim: PrimSummary) -> bool:
        return is_lidar_prim(prim)

    def extract_stage_parameters(self, prim: PrimSummary) -> Dict[str, Any]:
        if not is_lidar_prim(prim):
            raise ValueError(f"{prim.path} is not a detected RTX LiDAR Prim")
        result = dict(prim.attributes)
        result["typeName"] = prim.type_name
        result["appliedSchemas"] = list(prim.applied_schemas)
        return result

    def supported_modalities(self) -> Sequence[str]:
        return ("point_cloud", "point_cloud_ply")

    def validate(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndex]
    ) -> Sequence[ValidationIssue]:
        issues = []
        if not sensor.prim_path.startswith("/"):
            return (
                ValidationIssue(
                    "sensor.prim_path",
                    "LiDAR prim_path must be absolute",
                    f"sensors.{sensor.sensor_id}.prim_path",
                ),
            )
        if sensor.backend not in {"auto", "rtx_lidar"}:
            issues.append(
                ValidationIssue(
                    "sensor.lidar_backend",
                    "LiDAR backend must be auto or rtx_lidar",
                    f"sensors.{sensor.sensor_id}.backend",
                )
            )
        if stage_index is not None:
            prim = stage_index.get(sensor.prim_path)
            if prim is None:
                issues.append(
                    ValidationIssue(
                        "sensor.prim_missing",
                        "LiDAR Prim does not exist",
                        f"sensors.{sensor.sensor_id}.prim_path",
                    )
                )
            elif not is_lidar_prim(prim):
                issues.append(
                    ValidationIssue(
                        "sensor.prim_type",
                        f"Prim {prim.type_name} has no detected RTX LiDAR schema",
                        f"sensors.{sensor.sensor_id}.prim_path",
                    )
                )
        minimum = sensor.parameters.get("min_range")
        maximum = sensor.parameters.get("max_range")
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and isinstance(maximum, (int, float))
            and not isinstance(maximum, bool)
            and float(maximum) <= float(minimum)
        ):
            issues.append(
                ValidationIssue(
                    "sensor.lidar_range",
                    "max_range must be greater than min_range",
                    f"sensors.{sensor.sensor_id}.parameters",
                )
            )
        return issues

    def compile_runtime_payload(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndex]
    ) -> Dict[str, Any]:
        stage_parameters = dict(sensor.stage_parameters)
        if stage_index is not None:
            prim = stage_index.get(sensor.prim_path)
            if prim is not None and is_lidar_prim(prim):
                stage_parameters = self.extract_stage_parameters(prim)
        defaults = {
            "annotator": "IsaacExtractRTXSensorPointCloud",
            "output_coordinate_frame": "sensor",
            "scan_mode": "complete_scan",
            "points_unit": "meter",
        }
        overrides = {
            name: value
            for name, value in sensor.parameters.items()
            if sensor.parameter_sources.get(name, "override") == "override"
        }
        effective = dict(stage_parameters)
        for name, value in defaults.items():
            effective.setdefault(name, value)
        effective.update(overrides)
        sources = {name: "stage" for name in stage_parameters}
        for name in defaults:
            sources.setdefault(name, "default")
        sources.update({name: "override" for name in overrides})
        return {
            "sensor_id": sensor.sensor_id,
            "plugin": self.plugin_id,
            "plugin_version": self.manifest().plugin_version,
            "prim_path": sensor.prim_path,
            "stage_parameters": stage_parameters,
            "default_parameters": defaults,
            "override_parameters": overrides,
            "parameters": effective,
            "parameter_sources": sources,
            "backend": sensor.backend,
            "sync_group_id": sensor.sync_group_id or sensor.sensor_id,
        }

    def definition_from_prim(
        self, sensor_id: str, prim: PrimSummary
    ) -> SensorDefinition:
        parameters = self.extract_stage_parameters(prim)
        return SensorDefinition(
            sensor_id=sensor_id,
            plugin=self.plugin_id,
            plugin_version=self.manifest().plugin_version,
            prim_path=prim.path,
            stage_parameters=dict(parameters),
            parameters=dict(parameters),
            parameter_sources={name: "stage" for name in parameters},
        )

    def author_runtime_overrides(self, stage: Any, sensor: SensorDefinition):
        prim = stage.GetPrimAtPath(sensor.prim_path)
        if prim is None or not prim.IsValid():
            raise ValueError(f"LiDAR Prim does not exist: {sensor.prim_path}")
        authored = {}
        for name, value in sensor.parameters.items():
            if sensor.parameter_sources.get(name) != "override":
                continue
            if name in {
                "annotator",
                "output_coordinate_frame",
                "scan_mode",
                "points_unit",
            }:
                continue
            candidates = _OVERRIDE_ALIASES.get(name, (name,))
            attribute = next(
                (
                    prim.GetAttribute(candidate)
                    for candidate in candidates
                    if prim.GetAttribute(candidate).IsValid()
                ),
                None,
            )
            if attribute is None:
                raise ValueError(
                    f"LiDAR override has no authored USD attribute: {name}"
                )
            attribute.Set(value)
            authored[name] = value
        return authored

    def create_runtime_driver(
        self,
        sensor: SensorDefinition,
        *,
        resolution: Sequence[int],
        modalities: Sequence[str],
    ) -> Any:
        _ = resolution
        from semantic_world_v04.runtime.lidar_driver import RtxLidarRuntimeDriver

        return RtxLidarRuntimeDriver(sensor, modalities=modalities)


PLUGIN_CLASSES = (RtxLidarPlugin,)
