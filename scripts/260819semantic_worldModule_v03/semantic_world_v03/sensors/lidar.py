"""Isaac Sim 6 experimental RTX LiDAR driver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import ConfigurationError, SensorCaptureError
from ..models import (
    AcquisitionKind,
    CaptureRequest,
    PreflightIssue,
    PreflightReport,
    SensorCapabilities,
    SensorPacket,
    jsonable,
    stable_hash,
)
from .base import BaseSensorDriver, SensorRuntimeContext


_SUPPORTED_MODALITIES = {
    "generic_model_output",
    "point_cloud",
    "range",
    "intensity",
    "stable_id_map",
}


def _profile(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"LiDAR calibration profile does not exist: {source}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"LiDAR calibration profile must be an object: {source}")
    return raw


def _lidar_snapshot(stage: Any, path: str) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(path)
    if prim is None or not prim.IsValid():
        return {}
    attributes: dict[str, Any] = {}
    for attribute in prim.GetAttributes():
        name = str(attribute.GetName())
        if (
            name.startswith("omni:sensor:")
            or name.startswith("omni:simready:nonvisual:")
        ) and attribute.HasAuthoredValueOpinion():
            attributes[name] = jsonable(attribute.Get())
    return {
        "prim_path": path,
        "type_name": str(prim.GetTypeName()),
        "applied_schemas": [str(item) for item in prim.GetAppliedSchemas()],
        "attributes": attributes,
    }


class RtxLidarDriver(BaseSensorDriver):
    def __init__(self, spec: Any) -> None:
        super().__init__(spec)
        unknown = sorted(set(spec.modalities) - _SUPPORTED_MODALITIES)
        if unknown:
            raise ConfigurationError(
                f"RTX LiDAR {spec.sensor_id} has unsupported modalities: {', '.join(unknown)}"
            )
        self._authoring = None
        self._sensor = None
        self._annotators = ["generic-model-output"]
        if "stable_id_map" in spec.modalities:
            self._annotators.append("stable-id-map")

    @property
    def capabilities(self) -> SensorCapabilities:
        return SensorCapabilities(
            acquisition=AcquisitionKind.INTERVAL,
            modalities=self.spec.modalities,
            requires_render_trigger=False,
        )

    @property
    def prim_path(self) -> str:
        return self.spec.source.resolved_prim_path

    def _preflight(self, stage: Any) -> PreflightReport:
        issues: list[PreflightIssue] = []
        calibration_profile = _profile(self.spec.calibration.profile)
        prim = stage.GetPrimAtPath(self.prim_path)
        exists = prim is not None and prim.IsValid()
        if self.spec.source.mode == "existing_prim":
            if not exists:
                issues.append(
                    PreflightIssue(
                        "error", "lidar_prim_missing", f"RTX LiDAR prim is missing: {self.prim_path}", self.sensor_id
                    )
                )
            else:
                self.calibration = _lidar_snapshot(stage, self.prim_path)
                type_name = str(prim.GetTypeName())
                if "Lidar" not in type_name:
                    issues.append(
                        PreflightIssue(
                            "error", "wrong_prim_type", f"Expected OmniLidar at {self.prim_path}, got {type_name}", self.sensor_id
                        )
                    )
                for attribute_name in (
                    "omni:sensor:Core:scanRateBaseHz",
                    "omni:sensor:core:scanRateBaseHz",
                ):
                    attribute = prim.GetAttribute(attribute_name)
                    if attribute is not None and attribute.IsValid() and attribute.HasAuthoredValueOpinion():
                        stage_rate = float(attribute.Get())
                        if stage_rate != float(self.spec.clock.hz):
                            issues.append(
                                PreflightIssue(
                                    "error",
                                    "lidar_prim_tick_scan_rate_mismatch",
                                    f"LiDAR prim scan rate {stage_rate:g} must equal configured "
                                    f"clock.hz {self.spec.clock.hz:g}",
                                    self.sensor_id,
                                )
                            )
                        break
        else:
            parent = stage.GetPrimAtPath(str(self.spec.source.parent_prim))
            if parent is None or not parent.IsValid():
                issues.append(
                    PreflightIssue(
                        "error", "create_parent_missing",
                        f"LiDAR parent prim is missing: {self.spec.source.parent_prim}", self.sensor_id,
                    )
                )
            if exists:
                issues.append(
                    PreflightIssue(
                        "error", "create_prim_exists", f"LiDAR create target already exists: {self.prim_path}", self.sensor_id
                    )
                )
        configured_scan_rate = self.spec.settings.get("scan_rate_hz")
        if configured_scan_rate is not None and float(configured_scan_rate) != float(self.spec.clock.hz):
            issues.append(
                PreflightIssue(
                    "error",
                    "lidar_tick_scan_rate_mismatch",
                    f"LiDAR tick rate {self.spec.clock.hz:g} must equal scan_rate_hz {configured_scan_rate}",
                    self.sensor_id,
                )
            )
        if calibration_profile:
            self.calibration = {**self.calibration, "profile": calibration_profile}
        if self.calibration:
            self.calibration_hash = stable_hash(self.calibration)
            expected_hash = self.spec.calibration.expected_hash
            if expected_hash and expected_hash.removeprefix("sha256:") != self.calibration_hash:
                issues.append(
                    PreflightIssue(
                        "error", "calibration_hash_mismatch",
                        f"LiDAR calibration hash mismatch for {self.sensor_id}", self.sensor_id,
                    )
                )
        return PreflightReport(
            tuple(issues),
            {
                "prim_path": self.prim_path,
                "mode": self.spec.source.mode,
                "calibration": self.calibration,
            },
        )

    def _initialize(self, context: SensorRuntimeContext) -> None:
        from isaacsim.sensors.experimental.rtx import Lidar, LidarSensor

        source = self.spec.source
        aux_level = str(self.spec.settings.get("aux_output_level", "BASIC"))
        attributes = dict(self.spec.settings.get("attributes", {}))
        accumulate_outputs = bool(self.spec.settings.get("accumulate_outputs", True))
        if source.mode == "create":
            self._authoring = Lidar.create(
                self.prim_path,
                tick_rate=float(self.spec.clock.hz),
                aux_output_level=aux_level,
                accumulate_outputs=accumulate_outputs,
                attributes=attributes or None,
                config=source.config,
                usd_path=source.usd_path,
                variant=source.variant,
            )
        else:
            self._authoring = Lidar(
                self.prim_path,
                tick_rate=float(self.spec.clock.hz),
                aux_output_level=aux_level,
                accumulate_outputs=accumulate_outputs,
                attributes=attributes or None,
            )
        self._sensor = LidarSensor(self._authoring, annotators=self._annotators)
        self.calibration = {
            "prim_path": self.prim_path,
            "tick_rate_hz": self.spec.clock.hz,
            "sensor_type": self.sensor_type,
            "source_config": source.config,
            "source_usd": source.usd_path,
            "variant": source.variant,
            "settings": self.spec.settings,
            "prim": _lidar_snapshot(context.stage, self.prim_path),
            "profile": _profile(self.spec.calibration.profile),
        }
        self.calibration_hash = stable_hash(self.calibration)

    def read(self, request: CaptureRequest) -> SensorPacket:
        if self._sensor is None:
            raise SensorCaptureError(f"RTX LiDAR {self.sensor_id} is not initialized")
        raw, info = self._sensor.get_data("generic-model-output")
        if raw is None:
            raise SensorCaptureError(
                f"RTX LiDAR {self.sensor_id} has no complete scan for {request.capture_id}"
            )
        payloads: dict[str, Any] = {}
        requested = set(request.requested_modalities or self.spec.modalities)
        if "generic_model_output" in requested:
            payloads["generic_model_output"] = {"data": raw, "info": info}
        parsed_summary: Any = None
        try:
            from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data

            parsed = parse_generic_model_output_data(raw)
            parsed_values = (
                parsed
                if isinstance(parsed, dict)
                else {
                    name: getattr(parsed, name)
                    for name in dir(parsed)
                    if not name.startswith("_") and not callable(getattr(parsed, name, None))
                }
            )
            elements = parsed_values.get("elements")
            if elements is None:
                raise SensorCaptureError("GenericModelOutput has no elements structure")
            import numpy as np

            x = np.asarray(getattr(elements, "x", elements.get("x") if isinstance(elements, dict) else None))
            y = np.asarray(getattr(elements, "y", elements.get("y") if isinstance(elements, dict) else None))
            z = np.asarray(getattr(elements, "z", elements.get("z") if isinstance(elements, dict) else None))
            scalar = np.asarray(
                getattr(elements, "scalar", elements.get("scalar") if isinstance(elements, dict) else None)
            )
            coordinate_value = self.spec.settings.get(
                "coordinates", parsed_values.get("elementsCoordsType", "SPHERICAL")
            )
            coordinates = str(getattr(coordinate_value, "name", coordinate_value)).upper()
            if "CARTESIAN" in coordinates:
                points = np.column_stack((x, y, z))
                ranges = np.linalg.norm(points, axis=1)
            else:
                azimuth = np.deg2rad(x)
                elevation = np.deg2rad(y)
                cos_elevation = np.cos(elevation)
                points = np.column_stack(
                    (
                        z * cos_elevation * np.cos(azimuth),
                        z * cos_elevation * np.sin(azimuth),
                        z * np.sin(elevation),
                    )
                )
                ranges = z
            if "point_cloud" in requested:
                payloads["point_cloud"] = {"data": points, "info": info}
            if "range" in requested:
                payloads["range"] = {"data": ranges, "info": info}
            if "intensity" in requested:
                payloads["intensity"] = {"data": scalar, "info": info}
            parsed_summary = {
                "num_elements": int(parsed_values.get("numElements", len(x))),
                "coordinates": coordinates,
                "timestamp_ns": int(parsed_values.get("timestampNs", 0)),
                "frame_id": int(parsed_values.get("frameId", 0)),
            }
        except Exception as exc:
            if any(name in requested for name in ("point_cloud", "range", "intensity")):
                raise SensorCaptureError(
                    f"Could not parse requested LiDAR modalities for {self.sensor_id}: {exc}"
                ) from exc
            parsed_summary = {"parse_warning": str(exc)}
        if "stable_id_map" in requested and "stable-id-map" in self._annotators:
            stable_data, stable_info = self._sensor.get_data("stable-id-map")
            if stable_data is not None:
                try:
                    from isaacsim.sensors.experimental.rtx import parse_stable_id_map_data

                    stable_data = parse_stable_id_map_data(stable_data)
                except Exception:
                    pass
                payloads["stable_id_map"] = {"data": stable_data, "info": stable_info}
        if not payloads:
            raise SensorCaptureError(f"RTX LiDAR {self.sensor_id} produced no requested payloads")
        return SensorPacket(
            run_id=request.run_id,
            capture_id=request.capture_id,
            frame_id=request.frame_id,
            sample_id=request.sample_id,
            sensor_id=self.sensor_id,
            sensor_type=self.sensor_type,
            variant_id=request.variant_id,
            acquisition=AcquisitionKind.INTERVAL,
            timestamp=request.interval_end if request.interval_end is not None else request.snapshot.dataset_time,
            interval_start=request.interval_start,
            interval_end=request.interval_end,
            physics_step=request.snapshot.physics_step,
            world_state_hash=request.snapshot.state_hash,
            calibration_hash=self.calibration_hash,
            payloads=payloads,
            metadata={
                "prim_path": self.prim_path,
                "requested_modalities": list(self.spec.modalities),
                "generic_model_output_info": jsonable(info),
                "parsed_summary": parsed_summary,
            },
        )

    def _close(self) -> None:
        for value in (self._sensor, self._authoring):
            destroy = getattr(value, "destroy", None)
            if callable(destroy):
                destroy()
        self._sensor = None
        self._authoring = None
