"""Replicator camera driver for existing USD Camera Prim paths."""

from typing import Any, Dict, Iterable, Mapping, Sequence, Set

from semantic_world_v04.core.models import SensorDefinition
from semantic_world_v04.core.sensor_models import (
    CalibrationSnapshot,
    CaptureContext,
    SensorSample,
    TypedPayload,
    infer_shape,
)


class CameraRuntimeDriver:
    capture_trigger_key = "replicator_orchestrator"

    def __init__(
        self,
        sensor: SensorDefinition,
        *,
        resolution: Sequence[int],
        modalities: Iterable[str],
    ) -> None:
        self.sensor = sensor
        override = sensor.parameters.get("resolution")
        selected_resolution = override if override is not None else resolution
        if (
            not isinstance(selected_resolution, (list, tuple))
            or len(selected_resolution) != 2
        ):
            raise ValueError("camera resolution must contain width and height")
        self.resolution = (int(selected_resolution[0]), int(selected_resolution[1]))
        self.output_resolution = self.resolution
        self.modalities: Set[str] = set(modalities)
        unknown = self.modalities - {
            "rgb",
            "semantic_id",
            "semantic_color",
            "depth_linear",
            "depth_color",
            "surface_normal",
            "surface_normal_color",
            "instance_id",
            "instance_color",
        }
        if unknown:
            raise ValueError(
                f"unsupported camera modality: {', '.join(sorted(unknown))}"
            )
        self.render_product = None
        self.annotators: Dict[str, Any] = {}
        self.effective_parameters_snapshot: Dict[str, Any] = {}
        self.meters_per_unit = 1.0

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id

    def preflight(self, stage: Any) -> None:
        prim = stage.GetPrimAtPath(self.sensor.prim_path)
        if prim is None or not prim.IsValid():
            raise ValueError(f"camera Prim does not exist: {self.sensor.prim_path}")
        if str(prim.GetTypeName()) != "Camera":
            raise ValueError(
                f"sensor Prim is not a Camera: {self.sensor.prim_path}"
            )

    def initialize(self, stage: Any) -> None:
        self.preflight(stage)
        from semantic_world_v04.stage.omni_adapter import read_camera_parameters

        self.effective_parameters_snapshot = read_camera_parameters(
            stage, self.sensor.prim_path
        )
        try:
            from pxr import UsdGeom  # type: ignore

            self.meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage))
        except (ImportError, TypeError, ValueError):
            self.meters_per_unit = 1.0
        self.effective_parameters_snapshot["resolution"] = list(self.resolution)
        self.effective_parameters_snapshot["metersPerUnit"] = self.meters_per_unit
        import omni.replicator.core as rep  # type: ignore

        rep.orchestrator.set_capture_on_play(False)
        self.render_product = rep.create.render_product(
            self.sensor.prim_path,
            resolution=self.resolution,
            name=f"v04_{self.sensor.sensor_id}",
        )
        texture = getattr(self.render_product, "hydra_texture", None)
        if texture is not None:
            texture.set_updates_enabled(True)
        attached = []
        try:
            if "rgb" in self.modalities:
                annotator = rep.AnnotatorRegistry.get_annotator("rgb")
                annotator.attach(self.render_product)
                self.annotators["rgb"] = annotator
                attached.append(annotator)
            if {"semantic_id", "semantic_color"} & self.modalities:
                annotator = rep.AnnotatorRegistry.get_annotator(
                    "semantic_segmentation",
                    init_params={
                        "colorize": False,
                        "semanticFilter": "class:*",
                    },
                )
                annotator.attach(self.render_product)
                self.annotators["semantic"] = annotator
                attached.append(annotator)
            if {"depth_linear", "depth_color"} & self.modalities:
                annotator = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
                annotator.attach(self.render_product)
                self.annotators["depth_linear"] = annotator
                attached.append(annotator)
            if {"surface_normal", "surface_normal_color"} & self.modalities:
                annotator = rep.AnnotatorRegistry.get_annotator("normals")
                annotator.attach(self.render_product)
                self.annotators["surface_normal"] = annotator
                attached.append(annotator)
            if {"instance_id", "instance_color"} & self.modalities:
                annotator = rep.AnnotatorRegistry.get_annotator(
                    "instance_segmentation",
                    init_params={"colorize": False},
                )
                annotator.attach(self.render_product)
                self.annotators["instance"] = annotator
                attached.append(annotator)
        except BaseException:
            for annotator in reversed(attached):
                annotator.detach(self.render_product)
            self.annotators.clear()
            self.render_product.destroy()
            self.render_product = None
            raise

    def read(self, requested_modalities: Sequence[str]) -> Dict[str, Any]:
        if self.render_product is None:
            raise RuntimeError(f"camera {self.sensor_id} is not initialized")
        requested = set(requested_modalities)
        if not requested <= self.modalities:
            raise ValueError(
                f"camera {self.sensor_id} received undeclared modalities: "
                f"{sorted(requested - self.modalities)}"
            )
        result: Dict[str, Any] = {}
        if "rgb" in requested:
            value = self.annotators["rgb"].get_data()
            if value is None:
                raise RuntimeError(f"camera {self.sensor_id} returned no RGB data")
            result["rgb"] = value
        if {"semantic_id", "semantic_color"} & requested:
            value = self.annotators["semantic"].get_data()
            if isinstance(value, Mapping) and "data" in value:
                data = value.get("data")
                info = value.get("info", {})
            else:
                data = value
                info = {}
            if data is None:
                raise RuntimeError(
                    f"camera {self.sensor_id} returned no semantic data"
                )
            result["semantic"] = {"data": data, "info": info}
        if {"depth_linear", "depth_color"} & requested:
            value = self.annotators["depth_linear"].get_data()
            if value is None:
                raise RuntimeError(f"camera {self.sensor_id} returned no depth data")
            result["depth_linear"] = value * self.meters_per_unit
        if {"surface_normal", "surface_normal_color"} & requested:
            value = self.annotators["surface_normal"].get_data()
            if value is None:
                raise RuntimeError(f"camera {self.sensor_id} returned no normal data")
            try:
                if len(value.shape) == 3 and value.shape[-1] > 3:
                    value = value[..., :3]
            except (AttributeError, TypeError):
                pass
            result["surface_normal"] = value
        if {"instance_id", "instance_color"} & requested:
            value = self.annotators["instance"].get_data()
            if isinstance(value, Mapping) and "data" in value:
                data = value.get("data")
                info = value.get("info", {})
            else:
                data = value
                info = {}
            if data is None:
                raise RuntimeError(
                    f"camera {self.sensor_id} returned no instance data"
                )
            result["instance"] = {"data": data, "info": info}
        return result

    def trigger_capture(self, rt_subframes: int) -> None:
        """Render all Replicator-backed sensors once for this frame."""

        render_once(rt_subframes)

    def read_sample(
        self,
        requested_modalities: Sequence[str],
        context: CaptureContext,
    ) -> SensorSample:
        raw = self.read(requested_modalities)
        payloads: Dict[str, TypedPayload] = {}
        requested = set(requested_modalities)
        if "rgb" in raw:
            value = raw["rgb"]
            payloads["rgb"] = TypedPayload(
                kind="raster",
                data=value,
                dtype=str(getattr(value, "dtype", "uint8")),
                shape=infer_shape(value),
                coordinate_frame=self.sensor_id,
            )
        if "semantic" in raw:
            semantic = raw["semantic"]
            typed = TypedPayload(
                kind="dense_array",
                data=semantic["data"],
                dtype=str(getattr(semantic["data"], "dtype", "uint32")),
                shape=infer_shape(semantic["data"]),
                coordinate_frame=self.sensor_id,
                metadata={"info": semantic.get("info", {})},
            )
            for modality_id in requested & {"semantic_id", "semantic_color"}:
                payloads[modality_id] = typed
        if "depth_linear" in raw:
            value = raw["depth_linear"]
            typed = TypedPayload(
                kind="dense_array",
                data=value,
                dtype=str(getattr(value, "dtype", "float32")),
                shape=infer_shape(value),
                unit="meter",
                coordinate_frame=self.sensor_id,
            )
            for modality_id in requested & {"depth_linear", "depth_color"}:
                payloads[modality_id] = typed
        if "surface_normal" in raw:
            value = raw["surface_normal"]
            typed = TypedPayload(
                kind="dense_array",
                data=value,
                dtype=str(getattr(value, "dtype", "float32")),
                shape=infer_shape(value),
                coordinate_frame=self.sensor_id,
            )
            for modality_id in requested & {
                "surface_normal",
                "surface_normal_color",
            }:
                payloads[modality_id] = typed
        if "instance" in raw:
            instance = raw["instance"]
            typed = TypedPayload(
                kind="dense_array",
                data=instance["data"],
                dtype=str(getattr(instance["data"], "dtype", "uint32")),
                shape=infer_shape(instance["data"]),
                coordinate_frame=self.sensor_id,
                metadata={"info": instance.get("info", {})},
            )
            for modality_id in requested & {"instance_id", "instance_color"}:
                payloads[modality_id] = typed
        missing = requested - set(payloads)
        if missing:
            raise RuntimeError(
                f"camera {self.sensor_id} produced no typed payload for {sorted(missing)}"
            )
        return SensorSample(
            sensor_id=self.sensor_id,
            timestamp=context.capture_timestamp,
            modality_payloads=payloads,
            calibration_snapshot=self.calibration_snapshot(),
        )

    def calibration_snapshot(self) -> CalibrationSnapshot:
        parameters = dict(self.effective_parameters_snapshot)
        width, height = self.resolution
        focal = parameters.get("focalLength")
        horizontal = parameters.get("horizontalAperture")
        vertical = parameters.get("verticalAperture")
        if all(isinstance(item, (int, float)) for item in (focal, horizontal)):
            parameters["fx_pixels"] = float(focal) / float(horizontal) * width
        if all(isinstance(item, (int, float)) for item in (focal, vertical)):
            parameters["fy_pixels"] = float(focal) / float(vertical) * height
        parameters.setdefault("cx_pixels", width / 2.0)
        parameters.setdefault("cy_pixels", height / 2.0)
        model = (
            "native_fisheye"
            if self.sensor.plugin == "fisheye_camera"
            else "pinhole"
        )
        return CalibrationSnapshot(
            sensor_id=self.sensor_id,
            model=model,
            prim_path=self.sensor.prim_path,
            parameters=parameters,
            sensor_to_world=parameters.get("worldTransform", ()),
            coordinate_frame="world",
            meters_per_unit=self.meters_per_unit,
            backend_id=str(parameters.get("backend_id", "replicator_camera")),
        )

    def close(self) -> None:
        if self.render_product is None:
            return
        for annotator in reversed(list(self.annotators.values())):
            annotator.detach(self.render_product)
        self.annotators.clear()
        self.render_product.destroy()
        self.render_product = None


def render_once(rt_subframes: int) -> None:
    import omni.replicator.core as rep  # type: ignore

    rep.orchestrator.step(
        rt_subframes=rt_subframes,
        delta_time=0.0,
        pause_timeline=True,
        wait_for_render=True,
    )
    rep.orchestrator.wait_until_complete()
