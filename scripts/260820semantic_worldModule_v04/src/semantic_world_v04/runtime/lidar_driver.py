"""Version-isolated Replicator adapter for a pre-authored RTX LiDAR Prim."""

from typing import Any, Dict, Iterable, Mapping, Sequence, Set

from semantic_world_v04.core.models import SensorDefinition
from semantic_world_v04.core.sensor_models import (
    CalibrationSnapshot,
    CaptureContext,
    SensorSample,
    TypedPayload,
    infer_shape,
)

from .camera_driver import render_once


class RtxLidarRuntimeDriver:
    capture_trigger_key = "replicator_orchestrator"
    backend_id = "rtx_lidar"
    requires_continuous_history = True

    def __init__(
        self,
        sensor: SensorDefinition,
        *,
        modalities: Iterable[str],
    ) -> None:
        self.sensor = sensor
        self.modalities: Set[str] = set(modalities)
        unknown = self.modalities - {"point_cloud", "point_cloud_ply"}
        if unknown:
            raise ValueError(f"unsupported LiDAR modality: {sorted(unknown)}")
        self.render_product = None
        self.annotator = None
        self.effective_parameters_snapshot: Dict[str, Any] = {}
        self.meters_per_unit = 1.0

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id

    def preflight(self, stage: Any) -> None:
        prim = stage.GetPrimAtPath(self.sensor.prim_path)
        if prim is None or not prim.IsValid():
            raise ValueError(f"LiDAR Prim does not exist: {self.sensor.prim_path}")
        from semantic_world_v04.stage.omni_adapter import read_sensor_attributes

        values = read_sensor_attributes(stage, self.sensor.prim_path)
        haystack = " ".join(
            [
                str(values.get("typeName", "")),
                *[str(item) for item in values.get("appliedSchemas", [])],
                *[str(item) for item in values],
            ]
        ).casefold()
        if not any(term in haystack for term in ("lidar", "rtxsensor")):
            raise RuntimeError(
                f"Prim {self.sensor.prim_path} has no detected RTX LiDAR schema"
            )

    def initialize(self, stage: Any) -> None:
        self.preflight(stage)
        from semantic_world_v04.stage.omni_adapter import read_sensor_attributes

        self.effective_parameters_snapshot = read_sensor_attributes(
            stage, self.sensor.prim_path
        )
        self.effective_parameters_snapshot.update(self.sensor.parameters)
        self.effective_parameters_snapshot["backend_id"] = self.backend_id
        try:
            from pxr import UsdGeom  # type: ignore

            self.meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage))
        except (ImportError, TypeError, ValueError):
            self.meters_per_unit = 1.0
        self.effective_parameters_snapshot["metersPerUnit"] = self.meters_per_unit

        import omni.replicator.core as rep  # type: ignore
        import omni.kit.app  # type: ignore

        manager = omni.kit.app.get_app().get_extension_manager()
        manager.set_extension_enabled_immediate("isaacsim.sensors.rtx.nodes", True)
        rep.orchestrator.set_capture_on_play(False)
        self.render_product = rep.create.render_product(
            self.sensor.prim_path,
            # Isaac Sim 6's official RTX sensor Runtime uses 300x300.  The
            # texture is a scheduling surface; LiDAR output resolution comes
            # from the scan pattern, not these dimensions.
            resolution=(300, 300),
            name=f"v04_{self.sensor.sensor_id}",
        )
        annotator_name = str(
            self.sensor.parameters.get(
                "annotator", "IsaacExtractRTXSensorPointCloud"
            )
        )
        try:
            self.annotator = rep.AnnotatorRegistry.get_annotator(
                annotator_name,
                device="cuda",
                do_array_copy=False,
            )
            render_product_path = getattr(
                self.render_product, "path", self.render_product
            )
            self.annotator.attach([render_product_path])
        except BaseException:
            if self.render_product is not None:
                self.render_product.destroy()
                self.render_product = None
            self.annotator = None
            raise
        self.effective_parameters_snapshot["annotator"] = annotator_name

    def trigger_capture(self, rt_subframes: int) -> None:
        render_once(rt_subframes)

    def read(self, requested_modalities: Sequence[str]) -> Dict[str, Any]:
        if self.annotator is None:
            raise RuntimeError(f"LiDAR {self.sensor_id} is not initialized")
        requested = set(requested_modalities)
        if not requested <= self.modalities:
            raise ValueError(
                f"LiDAR {self.sensor_id} received undeclared modalities: "
                f"{sorted(requested - self.modalities)}"
            )
        raw = self.annotator.get_data()
        cloud = self._normalize_cloud(raw)
        return {"point_cloud": cloud}

    def _normalize_cloud(self, raw: Any) -> Mapping[str, Any]:
        import numpy as np

        def as_numpy(value: Any):
            if hasattr(value, "numpy"):
                value = value.numpy()
            return np.asarray(value)

        if raw is None:
            raise RuntimeError(f"LiDAR {self.sensor_id} returned no data")
        source = dict(raw) if isinstance(raw, Mapping) else {"data": raw}
        points = None
        for name in ("points", "pointCloud", "point_cloud", "xyz", "data"):
            if name not in source:
                continue
            candidate = as_numpy(source[name])
            if candidate.ndim == 2 and candidate.shape[1] >= 3:
                points = candidate[:, :3]
                break
            if candidate.ndim == 1 and candidate.size % 3 == 0:
                points = candidate.reshape((-1, 3))
                break
        if points is None and all(
            name in source for name in ("distance", "azimuth", "elevation")
        ):
            distance = as_numpy(source["distance"]).astype(
                np.float64, copy=False
            ).reshape(-1)
            azimuth = as_numpy(source["azimuth"]).astype(
                np.float64, copy=False
            ).reshape(-1)
            elevation = as_numpy(source["elevation"]).astype(
                np.float64, copy=False
            ).reshape(-1)
            if not (len(distance) == len(azimuth) == len(elevation)):
                raise RuntimeError("LiDAR polar arrays have different lengths")
            horizontal = distance * np.cos(elevation)
            points = np.column_stack(
                (
                    horizontal * np.cos(azimuth),
                    horizontal * np.sin(azimuth),
                    distance * np.sin(elevation),
                )
            )
        if points is None:
            raise RuntimeError(
                f"LiDAR {self.sensor_id} payload has no recognized XYZ or polar data; "
                f"fields={sorted(source)}"
            )
        points = np.asarray(points, dtype=np.float32)
        if self.sensor.parameters.get("points_unit", "meter") == "stage_unit":
            points *= self.meters_per_unit
        finite = np.isfinite(points).all(axis=1)
        points = points[finite]
        result: Dict[str, Any] = {"points": points}
        point_count = len(finite)
        for name, value in source.items():
            if name in {"points", "pointCloud", "point_cloud", "xyz", "data"}:
                continue
            if isinstance(value, Mapping):
                continue
            candidate = as_numpy(value)
            if candidate.ndim == 1 and len(candidate) == point_count:
                result[str(name)] = candidate[finite]
        if points.size == 0:
            raise RuntimeError(f"LiDAR {self.sensor_id} returned no finite points")
        return result

    def read_sample(
        self,
        requested_modalities: Sequence[str],
        context: CaptureContext,
    ) -> SensorSample:
        cloud = self.read(requested_modalities)["point_cloud"]
        points = cloud["points"]
        typed = TypedPayload(
            kind="point_cloud",
            data=cloud,
            dtype=str(getattr(points, "dtype", "float32")),
            shape=infer_shape(points),
            unit="meter",
            coordinate_frame=str(
                self.sensor.parameters.get("output_coordinate_frame", "sensor")
            ),
            fields=tuple(sorted(cloud)),
        )
        return SensorSample(
            sensor_id=self.sensor_id,
            timestamp=context.capture_timestamp,
            modality_payloads={name: typed for name in requested_modalities},
            calibration_snapshot=self.calibration_snapshot(),
            sequence_metadata={
                "scan_mode": self.sensor.parameters.get(
                    "scan_mode", "complete_scan"
                ),
                "point_count": int(len(points)),
            },
        )

    def calibration_snapshot(self) -> CalibrationSnapshot:
        parameters = dict(self.effective_parameters_snapshot)
        return CalibrationSnapshot(
            sensor_id=self.sensor_id,
            model="rtx_lidar_scan_pattern",
            prim_path=self.sensor.prim_path,
            parameters=parameters,
            coordinate_frame=str(
                self.sensor.parameters.get("output_coordinate_frame", "sensor")
            ),
            meters_per_unit=self.meters_per_unit,
            backend_id=self.backend_id,
        )

    def close(self) -> None:
        if self.annotator is not None and self.render_product is not None:
            render_product_path = getattr(
                self.render_product, "path", self.render_product
            )
            self.annotator.detach([render_product_path])
        self.annotator = None
        if self.render_product is not None:
            self.render_product.destroy()
            self.render_product = None
