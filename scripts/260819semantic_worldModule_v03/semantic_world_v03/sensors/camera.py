"""Isaac Sim 6 pinhole and OpenCV-fisheye camera drivers."""

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


_BASE_CAMERA_ATTRIBUTES = (
    "projection",
    "focalLength",
    "horizontalAperture",
    "verticalAperture",
    "horizontalApertureOffset",
    "verticalApertureOffset",
    "clippingRange",
    "focusDistance",
    "fStop",
    "shutter:open",
    "shutter:close",
    "exposure:fStop",
    "exposure:time",
    "exposure:iso",
)


_MODALITY_TO_ANNOTATOR = {
    "rgb": "rgb",
    "semantic_segmentation": "semantic_segmentation",
    "instance_segmentation": "instance_segmentation",
    "instance_id_segmentation": "instance_id_segmentation",
    "distance_to_camera": "distance_to_camera",
    "distance_to_image_plane": "distance_to_image_plane",
    "depth": "distance_to_camera",
    "normals": "normals",
    "motion_vectors": "motion_vectors",
    "pointcloud": "pointcloud",
    "bounding_box_2d_tight": "bounding_box_2d_tight",
    "bounding_box_2d_loose": "bounding_box_2d_loose",
    "bounding_box_3d": "bounding_box_3d",
}


def _prim(stage: Any, path: str) -> Any:
    prim = stage.GetPrimAtPath(path)
    if prim is None or not prim.IsValid():
        return None
    return prim


def _attribute_value(prim: Any, name: str) -> Any:
    attribute = prim.GetAttribute(name)
    if attribute is None or not attribute.IsValid() or not attribute.HasAuthoredValueOpinion():
        return None
    return jsonable(attribute.Get())


def _camera_snapshot(stage: Any, path: str, time_code: float | None = None) -> dict[str, Any]:
    prim = _prim(stage, path)
    if prim is None:
        raise ValueError(f"Camera prim does not exist: {path}")
    values = {
        name: value
        for name in _BASE_CAMERA_ATTRIBUTES
        if (value := _attribute_value(prim, name)) is not None
    }
    for attribute in prim.GetAttributes():
        name = str(attribute.GetName())
        if name.startswith("omni:lensdistortion:") and attribute.HasAuthoredValueOpinion():
            values[name] = jsonable(attribute.Get())
    transform: list[float] | None = None
    try:
        from pxr import Usd, UsdGeom

        usd_time = Usd.TimeCode.Default() if time_code is None else Usd.TimeCode(time_code)
        matrix = UsdGeom.XformCache(usd_time).GetLocalToWorldTransform(prim)
        transform = [float(matrix[row][column]) for row in range(4) for column in range(4)]
    except Exception:
        transform = None
    return {
        "prim_path": path,
        "type_name": str(prim.GetTypeName()),
        "applied_schemas": [str(item) for item in prim.GetAppliedSchemas()],
        "attributes": values,
        "world_transform": transform,
    }


def _load_calibration_profile(path: str) -> dict[str, Any]:
    resolved = Path(path)
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Calibration profile does not exist: {resolved}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Calibration profile must be an object: {resolved}")
    attributes = raw.get("attributes", {})
    schemas = raw.get("schemas", [])
    if not isinstance(attributes, dict) or not isinstance(schemas, list):
        raise ConfigurationError("Calibration profile schemas/attributes have invalid types")
    return raw


def _intrinsic_calibration_hash(snapshot: dict[str, Any]) -> str:
    return stable_hash(
        {key: value for key, value in snapshot.items() if key != "world_transform"}
    )


class BaseCameraDriver(BaseSensorDriver):
    expected_fisheye = False

    def __init__(self, spec: Any) -> None:
        super().__init__(spec)
        unknown = sorted(set(spec.modalities) - set(_MODALITY_TO_ANNOTATOR))
        if unknown:
            raise ConfigurationError(
                f"Camera {spec.sensor_id} has unsupported modalities: {', '.join(unknown)}"
            )
        self._authoring = None
        self._sensor = None
        self._direct_render_product = None
        self._direct_annotators: dict[str, Any] = {}
        self._annotators = tuple(_MODALITY_TO_ANNOTATOR[item] for item in spec.modalities)

    @property
    def capabilities(self) -> SensorCapabilities:
        return SensorCapabilities(
            acquisition=AcquisitionKind.SNAPSHOT,
            modalities=self.spec.modalities,
            requires_render_trigger=True,
        )

    @property
    def prim_path(self) -> str:
        return self.spec.source.resolved_prim_path

    def _preflight(self, stage: Any) -> PreflightReport:
        issues: list[PreflightIssue] = []
        details: dict[str, Any] = {"prim_path": self.prim_path}
        if self.spec.source.mode == "existing_prim":
            prim = _prim(stage, self.prim_path)
            if prim is None:
                issues.append(
                    PreflightIssue("error", "camera_prim_missing", f"Camera prim is missing: {self.prim_path}", self.sensor_id)
                )
            elif str(prim.GetTypeName()) != "Camera":
                issues.append(
                    PreflightIssue("error", "wrong_prim_type", f"Expected Camera at {self.prim_path}, got {prim.GetTypeName()}", self.sensor_id)
                )
            else:
                self.calibration = _camera_snapshot(stage, self.prim_path)
                details["camera"] = self.calibration
                schemas = self.calibration.get("applied_schemas", [])
                has_fisheye = any("OpenCvFisheye" in item for item in schemas)
                has_fisheye_attrs = any(
                    name.startswith("omni:lensdistortion:opencvFisheye:")
                    for name in self.calibration.get("attributes", {})
                )
                if self.expected_fisheye and not (has_fisheye or has_fisheye_attrs):
                    issues.append(
                        PreflightIssue(
                            "error",
                            "fisheye_schema_missing",
                            f"Camera {self.prim_path} has no OmniLensDistortionOpenCvFisheyeAPI data",
                            self.sensor_id,
                        )
                    )
                if not self.expected_fisheye and has_fisheye:
                    issues.append(
                        PreflightIssue(
                            "warning",
                            "pinhole_has_fisheye_schema",
                            f"Pinhole driver is bound to fisheye camera {self.prim_path}",
                            self.sensor_id,
                        )
                    )
        else:
            details["creation"] = {
                "prim_path": self.prim_path,
                "calibration_policy": self.spec.calibration.policy,
            }
            parent = _prim(stage, str(self.spec.source.parent_prim))
            if parent is None:
                issues.append(
                    PreflightIssue(
                        "error", "create_parent_missing",
                        f"Sensor parent prim is missing: {self.spec.source.parent_prim}",
                        self.sensor_id,
                    )
                )
            if _prim(stage, self.prim_path) is not None:
                issues.append(
                    PreflightIssue(
                        "error",
                        "create_prim_exists",
                        f"Sensor create target already exists: {self.prim_path}",
                        self.sensor_id,
                    )
                )
            if self.expected_fisheye and self.spec.calibration.policy not in {
                "from_profile", "inline", "explicit_override"
            }:
                issues.append(
                    PreflightIssue(
                        "error",
                        "fisheye_creation_calibration_missing",
                        "Creating a fisheye camera requires from_profile, inline, or explicit_override calibration",
                        self.sensor_id,
                    )
                )
        if self.spec.calibration.expected_model:
            model = "opencv_fisheye" if self.expected_fisheye else "pinhole"
            if model != self.spec.calibration.expected_model:
                issues.append(
                    PreflightIssue(
                        "error",
                        "calibration_model_mismatch",
                        f"Expected model {self.spec.calibration.expected_model}, resolved {model}",
                        self.sensor_id,
                    )
                )
        if self.calibration:
            self.calibration_hash = _intrinsic_calibration_hash(self.calibration)
            expected_hash = self.spec.calibration.expected_hash
            if expected_hash:
                normalized = expected_hash.removeprefix("sha256:")
                if normalized != self.calibration_hash:
                    issues.append(
                        PreflightIssue(
                            "error",
                            "calibration_hash_mismatch",
                            f"Camera calibration hash mismatch for {self.sensor_id}",
                            self.sensor_id,
                        )
                    )
        return PreflightReport(tuple(issues), details)

    def _creation_parameters(self) -> tuple[list[str], dict[str, Any]]:
        schemas: list[str] = []
        attributes: dict[str, Any] = {}
        calibration = self.spec.calibration
        if calibration.profile:
            profile = _load_calibration_profile(calibration.profile)
            schemas.extend(str(item) for item in profile.get("schemas", []))
            attributes.update(profile.get("attributes", {}))
        schemas.extend(str(item) for item in self.spec.settings.get("schemas", []))
        attributes.update(calibration.attributes)
        attributes.update(self.spec.settings.get("attributes", {}))
        if self.expected_fisheye and "OmniLensDistortionOpenCvFisheyeAPI" not in schemas:
            schemas.append("OmniLensDistortionOpenCvFisheyeAPI")
        return list(dict.fromkeys(schemas)), attributes

    def _initialize(self, context: SensorRuntimeContext) -> None:
        from isaacsim.sensors.experimental.rtx import CameraSensor, RtxCamera

        schemas, attributes = self._creation_parameters()
        source = self.spec.source
        tick_rate = float(self.spec.clock.hz)
        assert self.spec.resolution is not None
        width, height = self.spec.resolution
        if source.mode == "create":
            self._authoring = RtxCamera.create(
                self.prim_path,
                tick_rate=tick_rate,
                schemas=schemas or None,
                attributes=attributes or None,
                config=source.config,
                usd_path=source.usd_path,
                variant=source.variant,
            )
        else:
            prim = _prim(context.stage, self.prim_path)
            assert prim is not None
            if "OmniSensorAPI" not in {str(item) for item in prim.GetAppliedSchemas()}:
                # Existing production stages commonly contain a plain
                # UsdGeom.Camera. The experimental RtxCamera wrapper rejects
                # such prims, so use Replicator's proven RenderProduct path.
                # This reads the authored camera/lens data directly and writes
                # no schema or calibration override to the source Stage.
                import omni.replicator.core as rep

                rep.orchestrator.set_capture_on_play(False)
                self._direct_render_product = rep.create.render_product(
                    self.prim_path,
                    resolution=(width, height),
                    name=f"v03_{self.sensor_id}",
                )
                texture = getattr(self._direct_render_product, "hydra_texture", None)
                if texture is not None:
                    texture.set_updates_enabled(True)
                attached: list[Any] = []
                try:
                    for configured_name, annotator_name in zip(
                        self.spec.modalities, self._annotators
                    ):
                        kwargs: dict[str, Any] = {}
                        if annotator_name == "semantic_segmentation":
                            kwargs["init_params"] = {
                                "colorize": False,
                                "semanticFilter": "class:*",
                            }
                        annotator = rep.AnnotatorRegistry.get_annotator(
                            annotator_name, **kwargs
                        )
                        annotator.attach(self._direct_render_product)
                        self._direct_annotators[configured_name] = annotator
                        attached.append(annotator)
                except BaseException:
                    for annotator in reversed(attached):
                        annotator.detach(self._direct_render_product)
                    self._direct_annotators.clear()
                    self._direct_render_product.destroy()
                    self._direct_render_product = None
                    raise
                self.calibration = _camera_snapshot(context.stage, self.prim_path)
                self.calibration_hash = _intrinsic_calibration_hash(self.calibration)
                return
            kwargs: dict[str, Any] = {"tick_rate": tick_rate}
            if self.spec.calibration.policy == "explicit_override":
                kwargs["schemas"] = schemas or None
                kwargs["attributes"] = attributes or None
            kwargs["reset_xform_op_properties"] = False
            self._authoring = RtxCamera(self.prim_path, **kwargs)
        self._sensor = CameraSensor(
            self._authoring,
            resolution=(height, width),
            annotators=list(dict.fromkeys(self._annotators)),
        )
        self.calibration = _camera_snapshot(context.stage, self.prim_path)
        self.calibration_hash = _intrinsic_calibration_hash(self.calibration)

    def _warmup(self) -> None:
        assert self.runtime is not None
        count = int(self.spec.settings.get("warmup_frames", 0))
        if count:
            self.runtime.render_backend.update(count)

    def read(self, request: CaptureRequest) -> SensorPacket:
        if (
            self._sensor is None
            and self._direct_render_product is None
        ) or self.runtime is None:
            raise SensorCaptureError(f"Camera {self.sensor_id} is not initialized")
        payloads: dict[str, Any] = {}
        annotator_info: dict[str, Any] = {}
        requested = set(request.requested_modalities or self.spec.modalities)
        for configured_name, annotator_name in zip(self.spec.modalities, self._annotators):
            if configured_name not in requested:
                continue
            if self._sensor is not None:
                data, info = self._sensor.get_data(annotator_name)
            else:
                value = self._direct_annotators[configured_name].get_data()
                if isinstance(value, dict) and "data" in value:
                    data = value.get("data")
                    info = value.get("info", {})
                else:
                    data, info = value, {}
            if data is None:
                raise SensorCaptureError(
                    f"Camera {self.sensor_id} returned no {annotator_name} data for {request.capture_id}"
                )
            payloads[configured_name] = {"data": data, "info": info}
            annotator_info[configured_name] = jsonable(info)
        time_code = request.snapshot.timeline_time * float(
            self.runtime.stage.GetTimeCodesPerSecond()
        )
        live_calibration = _camera_snapshot(self.runtime.stage, self.prim_path, time_code)
        return SensorPacket(
            run_id=request.run_id,
            capture_id=request.capture_id,
            frame_id=request.frame_id,
            sample_id=request.sample_id,
            sensor_id=self.sensor_id,
            sensor_type=self.sensor_type,
            variant_id=request.variant_id,
            acquisition=AcquisitionKind.SNAPSHOT,
            timestamp=request.snapshot.dataset_time,
            physics_step=request.snapshot.physics_step,
            world_state_hash=request.snapshot.state_hash,
            calibration_hash=self.calibration_hash,
            payloads=payloads,
            metadata={
                "prim_path": self.prim_path,
                "resolution_width_height": list(self.spec.resolution or ()),
                "camera_state": live_calibration,
                "annotator_info": annotator_info,
            },
        )

    def _close(self) -> None:
        if self._direct_render_product is not None:
            for annotator in reversed(tuple(self._direct_annotators.values())):
                annotator.detach(self._direct_render_product)
            self._direct_annotators.clear()
            self._direct_render_product.destroy()
            self._direct_render_product = None
        for value in (self._sensor, self._authoring):
            destroy = getattr(value, "destroy", None)
            if callable(destroy):
                destroy()
        self._sensor = None
        self._authoring = None


class PinholeCameraDriver(BaseCameraDriver):
    expected_fisheye = False


class FisheyeCameraDriver(BaseCameraDriver):
    expected_fisheye = True
