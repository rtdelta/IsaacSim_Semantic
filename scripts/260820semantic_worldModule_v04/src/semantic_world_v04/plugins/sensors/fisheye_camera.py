"""Fisheye camera definition using a pre-authored native USD lens model."""

from typing import Any, Dict, Optional, Sequence

from semantic_world_v04.core.models import SensorDefinition, ValidationIssue
from semantic_world_v04.core.sensor_models import (
    PluginManifest,
    SensorCapabilities,
    parameter_schema,
)
from semantic_world_v04.stage.index import PrimSummary, StageIndex

from .pinhole_camera import PinholeCameraPlugin

_PROJECTION_NAMES = {
    "cameraprojectiontype",
    "projectiontype",
    "projection_model",
    "omni:lensdistortion:model",
}
_FISHEYE_TERMS = ("fisheye", "ftheta", "opencvfish", "equirectangular")
_BASE_CAMERA_KEYS = {
    "focalLength",
    "horizontalAperture",
    "verticalAperture",
    "horizontalApertureOffset",
    "verticalApertureOffset",
    "clippingRange",
    "focusDistance",
    "fStop",
    "transform",
}
_FISHEYE_OVERRIDE_ALIASES = {
    "projection_model": ("omni:lensdistortion:model", "cameraProjectionType"),
    "cx": ("omni:lensdistortion:opencvFisheye:cx", "opticalCenterX"),
    "cy": ("omni:lensdistortion:opencvFisheye:cy", "opticalCenterY"),
    "fx": ("omni:lensdistortion:opencvFisheye:fx",),
    "fy": ("omni:lensdistortion:opencvFisheye:fy",),
    "k1": ("omni:lensdistortion:opencvFisheye:k1", "polyK1"),
    "k2": ("omni:lensdistortion:opencvFisheye:k2", "polyK2"),
    "k3": ("omni:lensdistortion:opencvFisheye:k3", "polyK3"),
    "k4": ("omni:lensdistortion:opencvFisheye:k4", "polyK4"),
    "image_size": ("omni:lensdistortion:opencvFisheye:imageSize",),
}


def detected_projection(parameters: Dict[str, Any]) -> str:
    for name, value in parameters.items():
        folded_name = str(name).casefold()
        folded_value = str(value).casefold()
        if any(term in folded_value for term in _FISHEYE_TERMS) and any(
            marker in folded_name
            for marker in ("schema", "model", "projection", "lens")
        ):
            return str(value)
        if folded_name in _PROJECTION_NAMES or "projection" in folded_name:
            if any(term in folded_value for term in _FISHEYE_TERMS):
                return str(value)
        if any(term in folded_name for term in _FISHEYE_TERMS):
            return str(parameters.get("projection_model", "native_fisheye"))
    return ""


class FisheyeCameraPlugin:
    plugin_id = "fisheye_camera"

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id,
            plugin_kind="sensor",
            plugin_version="1.0.0",
            display_name="Fisheye Camera",
            definition_class=f"{__name__}:FisheyeCameraPlugin",
            runtime_requirements=("replicator", "rtx", "native_fisheye_usd"),
            supported_modalities=tuple(self.supported_modalities()),
        )

    def capabilities(self) -> SensorCapabilities:
        return SensorCapabilities(
            payload_kinds=("raster", "dense_array"),
            time_model="instantaneous",
            trigger_domain="replicator_orchestrator",
            synchronization_mode="shared_trigger",
            calibration_model="native_fisheye",
            backend_requirements=("native_fisheye_usd", "omni.replicator.core"),
        )

    def parameter_schema(self) -> Dict[str, Any]:
        return parameter_schema(
            {
                "projection_model": {"type": "string"},
                "cx": {"type": "number"},
                "cy": {"type": "number"},
                "fx": {"type": "number", "minimum": 0.0},
                "fy": {"type": "number", "minimum": 0.0},
                "k1": {"type": "number"},
                "k2": {"type": "number"},
                "k3": {"type": "number"},
                "k4": {"type": "number"},
                "image_size": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "integer", "minimum": 1},
                },
                "focalLength": {"type": "number", "minimum": 0.0},
                "horizontalAperture": {"type": "number", "minimum": 0.0},
                "verticalAperture": {"type": "number", "minimum": 0.0},
                "clippingRange": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "number"},
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
        parameters = dict(prim.attributes)
        parameters["appliedSchemas"] = list(prim.applied_schemas)
        return prim.type_name == "Camera" and bool(detected_projection(parameters))

    def extract_stage_parameters(self, prim: PrimSummary) -> Dict[str, Any]:
        if prim.type_name != "Camera":
            raise ValueError(f"{prim.path} is not a USD Camera")
        parameters = dict(prim.attributes)
        parameters["appliedSchemas"] = list(prim.applied_schemas)
        projection = detected_projection(parameters)
        if projection:
            parameters.setdefault("projection_model", projection)
        return parameters

    def supported_modalities(self) -> Sequence[str]:
        return PinholeCameraPlugin().supported_modalities()

    def validate(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndex]
    ) -> Sequence[ValidationIssue]:
        issues = []
        if not sensor.prim_path.startswith("/"):
            return (
                ValidationIssue(
                    "sensor.prim_path",
                    "fisheye camera prim_path must be absolute",
                    f"sensors.{sensor.sensor_id}.prim_path",
                ),
            )
        effective = dict(sensor.stage_parameters)
        effective.update(sensor.parameters)
        if stage_index is not None:
            prim = stage_index.get(sensor.prim_path)
            if prim is None:
                issues.append(
                    ValidationIssue(
                        "sensor.prim_missing",
                        "fisheye Camera Prim does not exist",
                        f"sensors.{sensor.sensor_id}.prim_path",
                    )
                )
                return issues
            if prim.type_name != "Camera":
                issues.append(
                    ValidationIssue(
                        "sensor.prim_type",
                        f"expected Camera Prim, found {prim.type_name}",
                        f"sensors.{sensor.sensor_id}.prim_path",
                    )
                )
                return issues
            effective = self.extract_stage_parameters(prim)
            effective.update(sensor.parameters)
        if not detected_projection(effective):
            issues.append(
                ValidationIssue(
                    "sensor.fisheye_projection_missing",
                    "no native fisheye projection/lens attributes were found",
                    f"sensors.{sensor.sensor_id}.parameters",
                    hint=(
                        "author a supported native fisheye model on the USD Camera "
                        "or provide a verified projection_model override"
                    ),
                )
            )
        if sensor.backend not in {"auto", "native_usd"}:
            issues.append(
                ValidationIssue(
                    "sensor.fisheye_backend",
                    "fisheye backend must be auto or native_usd",
                    f"sensors.{sensor.sensor_id}.backend",
                )
            )
        return issues

    def compile_runtime_payload(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndex]
    ) -> Dict[str, Any]:
        stage_parameters = dict(sensor.stage_parameters)
        if stage_index is not None:
            prim = stage_index.get(sensor.prim_path)
            if prim is not None and prim.type_name == "Camera":
                stage_parameters = self.extract_stage_parameters(prim)
        overrides = {
            name: value
            for name, value in sensor.parameters.items()
            if sensor.parameter_sources.get(name, "override") == "override"
        }
        merged = dict(stage_parameters)
        merged.update(overrides)
        sources = {name: "stage" for name in stage_parameters}
        sources.update({name: "override" for name in overrides})
        return {
            "sensor_id": sensor.sensor_id,
            "plugin": self.plugin_id,
            "plugin_version": self.manifest().plugin_version,
            "prim_path": sensor.prim_path,
            "stage_parameters": stage_parameters,
            "default_parameters": {},
            "override_parameters": overrides,
            "parameters": merged,
            "parameter_sources": sources,
            "backend": sensor.backend,
            "sync_group_id": sensor.sync_group_id or sensor.sensor_id,
        }

    def definition_from_prim(
        self, sensor_id: str, prim: PrimSummary
    ) -> SensorDefinition:
        parameters = self.extract_stage_parameters(prim)
        if not detected_projection(parameters):
            raise ValueError(f"{prim.path} has no detected native fisheye model")
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
        base_sensor = SensorDefinition(
            sensor_id=sensor.sensor_id,
            plugin="pinhole_camera",
            prim_path=sensor.prim_path,
            parameters={
                key: value
                for key, value in sensor.parameters.items()
                if key in _BASE_CAMERA_KEYS
            },
            parameter_sources=dict(sensor.parameter_sources),
        )
        authored = PinholeCameraPlugin().author_runtime_overrides(stage, base_sensor)
        prim = stage.GetPrimAtPath(sensor.prim_path)
        for name, value in sensor.parameters.items():
            if (
                sensor.parameter_sources.get(name) != "override"
                or name in _BASE_CAMERA_KEYS
                or name == "resolution"
            ):
                continue
            candidates = _FISHEYE_OVERRIDE_ALIASES.get(name, (name,))
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
                    f"fisheye override attribute is not authored on the Prim: {name}"
                )
            if name == "image_size":
                from pxr import Gf  # type: ignore

                value = Gf.Vec2i(int(value[0]), int(value[1]))
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
        from semantic_world_v04.runtime.fisheye_driver import FisheyeRuntimeDriver

        return FisheyeRuntimeDriver(
            sensor,
            resolution=resolution,
            modalities=modalities,
        )


PLUGIN_CLASSES = (FisheyeCameraPlugin,)
