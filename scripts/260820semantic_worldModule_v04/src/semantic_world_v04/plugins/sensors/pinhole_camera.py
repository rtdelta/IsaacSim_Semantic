"""USD Camera discovery and compilation without importing Kit."""

from typing import Any, Dict, Optional, Sequence

from semantic_world_v04.core.models import SensorDefinition, ValidationIssue
from semantic_world_v04.core.sensor_models import (
    PluginManifest,
    SensorCapabilities,
    parameter_schema,
)
from semantic_world_v04.stage.index import PrimSummary, StageIndex

_CAMERA_ATTRIBUTES = (
    "focalLength",
    "horizontalAperture",
    "verticalAperture",
    "horizontalApertureOffset",
    "verticalApertureOffset",
    "clippingRange",
    "focusDistance",
    "fStop",
    "projection",
    "transform",
)

_AUTHORABLE_CAMERA_ATTRIBUTES = {
    "focalLength",
    "horizontalAperture",
    "verticalAperture",
    "horizontalApertureOffset",
    "verticalApertureOffset",
    "clippingRange",
    "focusDistance",
    "fStop",
    "projection",
    "transform",
}
_SUPPORTED_PARAMETERS = _AUTHORABLE_CAMERA_ATTRIBUTES | {"resolution"}


class PinholeCameraPlugin:
    plugin_id = "pinhole_camera"

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id,
            plugin_kind="sensor",
            plugin_version="2.0.0",
            display_name="Pinhole Camera",
            definition_class=f"{__name__}:PinholeCameraPlugin",
            runtime_requirements=("replicator", "rtx"),
            supported_modalities=tuple(self.supported_modalities()),
        )

    def capabilities(self) -> SensorCapabilities:
        return SensorCapabilities(
            payload_kinds=("raster", "dense_array"),
            time_model="instantaneous",
            trigger_domain="replicator_orchestrator",
            synchronization_mode="shared_trigger",
            calibration_model="pinhole",
            backend_requirements=("omni.replicator.core",),
        )

    def parameter_schema(self) -> Dict[str, Any]:
        return parameter_schema(
            {
                "focalLength": {"type": "number", "minimum": 0.0},
                "horizontalAperture": {"type": "number", "minimum": 0.0},
                "verticalAperture": {"type": "number", "minimum": 0.0},
                "horizontalApertureOffset": {"type": "number"},
                "verticalApertureOffset": {"type": "number"},
                "clippingRange": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "number"},
                },
                "focusDistance": {"type": "number", "minimum": 0.0},
                "fStop": {"type": "number", "minimum": 0.0},
                "projection": {
                    "type": "string",
                    "enum": ["perspective", "orthographic"],
                },
                "resolution": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "integer", "minimum": 1},
                },
            }
        )

    def matches_prim(self, prim: PrimSummary) -> bool:
        return prim.type_name == "Camera"

    def extract_stage_parameters(self, prim: PrimSummary) -> Dict[str, Any]:
        if not self.matches_prim(prim):
            raise ValueError(f"{prim.path} is not a USD Camera")
        return {
            key: prim.attributes[key]
            for key in _CAMERA_ATTRIBUTES
            if key in prim.attributes
        }

    def supported_modalities(self) -> Sequence[str]:
        return (
            "rgb",
            "semantic_id",
            "semantic_color",
            "depth_linear",
            "depth_color",
            "surface_normal",
            "surface_normal_color",
            "instance_id",
            "instance_color",
        )

    def create_runtime_driver(
        self,
        sensor: SensorDefinition,
        *,
        resolution: Sequence[int],
        modalities: Sequence[str],
    ) -> Any:
        """Create the delayed-import Runtime adapter for this plugin."""

        from semantic_world_v04.runtime.camera_driver import CameraRuntimeDriver

        return CameraRuntimeDriver(
            sensor,
            resolution=resolution,
            modalities=modalities,
        )

    def validate(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndex]
    ) -> Sequence[ValidationIssue]:
        issues = []
        if not sensor.prim_path.startswith("/"):
            issues.append(
                ValidationIssue(
                    "sensor.prim_path",
                    "camera prim_path must be an absolute USD Prim path",
                    f"sensors.{sensor.sensor_id}.prim_path",
                )
            )
            return issues
        if stage_index is not None:
            prim = stage_index.get(sensor.prim_path)
            if prim is None:
                issues.append(
                    ValidationIssue(
                        "sensor.prim_missing",
                        "camera Prim does not exist in the Stage",
                        f"sensors.{sensor.sensor_id}.prim_path",
                    )
                )
            elif not self.matches_prim(prim):
                issues.append(
                    ValidationIssue(
                        "sensor.prim_type",
                        f"expected Camera Prim, found {prim.type_name}",
                        f"sensors.{sensor.sensor_id}.prim_path",
                    )
                )
        unknown_sources = sorted(
            value
            for value in sensor.parameter_sources.values()
            if value not in {"stage", "override", "default"}
        )
        if unknown_sources:
            issues.append(
                ValidationIssue(
                    "sensor.parameter_source",
                    f"unknown parameter source(s): {', '.join(unknown_sources)}",
                    f"sensors.{sensor.sensor_id}.parameter_sources",
                )
            )
        unsupported_overrides = sorted(
            key
            for key, source in sensor.parameter_sources.items()
            if source == "override" and key not in _SUPPORTED_PARAMETERS
        )
        if unsupported_overrides:
            issues.append(
                ValidationIssue(
                    "sensor.parameter_override",
                    (
                        "unsupported camera override(s): "
                        + ", ".join(unsupported_overrides)
                    ),
                    f"sensors.{sensor.sensor_id}.parameters",
                )
            )
        return issues

    def compile_runtime_payload(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndex]
    ) -> Dict[str, Any]:
        stage_parameters: Dict[str, Any] = dict(sensor.stage_parameters)
        if stage_index is not None:
            prim = stage_index.get(sensor.prim_path)
            if prim is not None and self.matches_prim(prim):
                stage_parameters = self.extract_stage_parameters(prim)
        if not stage_parameters:
            stage_parameters = {
                key: value
                for key, value in sensor.parameters.items()
                if sensor.parameter_sources.get(key) == "stage"
            }
        merged = dict(stage_parameters)
        merged.update(sensor.parameters)
        sources = {key: "stage" for key in stage_parameters}
        sources.update(sensor.parameter_sources)
        for key in sensor.parameters:
            sources.setdefault(key, "override")
        return {
            "sensor_id": sensor.sensor_id,
            "plugin": self.plugin_id,
            "prim_path": sensor.prim_path,
            "stage_parameters": stage_parameters,
            "parameters": merged,
            "parameter_sources": sources,
        }

    def definition_from_prim(
        self, sensor_id: str, prim: PrimSummary
    ) -> SensorDefinition:
        parameters = self.extract_stage_parameters(prim)
        return SensorDefinition(
            sensor_id=sensor_id,
            plugin=self.plugin_id,
            prim_path=prim.path,
            stage_parameters=dict(parameters),
            parameters=parameters,
            parameter_sources={key: "stage" for key in parameters},
        )

    def runtime_override_parameters(
        self, sensor: SensorDefinition
    ) -> Dict[str, Any]:
        """Return only USD-authored overrides; resolution stays driver-owned."""

        return {
            key: value
            for key, value in sensor.parameters.items()
            if sensor.parameter_sources.get(key) == "override"
            and key in _AUTHORABLE_CAMERA_ATTRIBUTES
        }

    def author_runtime_overrides(
        self, stage: Any, sensor: SensorDefinition
    ) -> Dict[str, Any]:
        """Author camera overrides into the caller-selected Session edit layer."""

        from pxr import Gf, UsdGeom  # type: ignore

        prim = stage.GetPrimAtPath(sensor.prim_path)
        if prim is None or not prim.IsValid() or str(prim.GetTypeName()) != "Camera":
            raise ValueError(f"camera Prim does not exist: {sensor.prim_path}")
        values = self.runtime_override_parameters(sensor)
        camera = UsdGeom.Camera(prim)
        attributes = {
            "focalLength": camera.GetFocalLengthAttr(),
            "horizontalAperture": camera.GetHorizontalApertureAttr(),
            "verticalAperture": camera.GetVerticalApertureAttr(),
            "horizontalApertureOffset": camera.GetHorizontalApertureOffsetAttr(),
            "verticalApertureOffset": camera.GetVerticalApertureOffsetAttr(),
            "clippingRange": camera.GetClippingRangeAttr(),
            "focusDistance": camera.GetFocusDistanceAttr(),
            "fStop": camera.GetFStopAttr(),
            "projection": camera.GetProjectionAttr(),
        }
        for name, value in values.items():
            if name == "transform":
                rows = _matrix_rows(value)
                matrix = Gf.Matrix4d(*[number for row in rows for number in row])
                UsdGeom.Xformable(prim).MakeMatrixXform().Set(matrix)
            elif name == "clippingRange":
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    raise ValueError("clippingRange override must contain near and far")
                attributes[name].Set(Gf.Vec2f(float(value[0]), float(value[1])))
            elif name == "projection":
                attributes[name].Set(str(value))
            else:
                attributes[name].Set(float(value))
        return values


def _matrix_rows(value: Any):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 4
        or any(not isinstance(row, (list, tuple)) or len(row) != 4 for row in value)
    ):
        raise ValueError("transform override must be a 4x4 numeric matrix")
    try:
        return [[float(number) for number in row] for row in value]
    except (TypeError, ValueError) as exc:
        raise ValueError("transform override must be a 4x4 numeric matrix") from exc


PLUGIN_CLASSES = (PinholeCameraPlugin,)
