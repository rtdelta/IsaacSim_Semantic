"""Persistent semantic-camera RenderProduct and frame-level capture scheduling."""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import Any

import omni.replicator.core as rep
from omni.replicator.core.backends import DiskBackend
from pxr import Usd, UsdGeom

from capture_context import CaptureContext, CaptureReceipt
from semantic_dataset_writer import SemanticDatasetWriter


class CameraSchedulerState(Enum):
    CREATED = auto()
    RENDER_PRODUCT_READY = auto()
    WARMED = auto()
    WRITER_ATTACHED = auto()
    CAPTURING = auto()
    CLOSED = auto()


def _usd_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return str(value)


class SemanticCameraScheduler:
    """Own one persistent Camera RenderProduct and its dataset Writer."""

    def __init__(
        self,
        simulation_app: Any,
        stage: Any,
        camera_path: str,
        output_path: Path,
        mapping_path: Path,
        width: int,
        height: int,
        rt_subframes: int,
        save_runtime_ids: bool,
        strict_mapping: bool,
    ) -> None:
        self._app = simulation_app
        self._stage = stage
        self._requested_camera_path = camera_path
        self._output_path = Path(output_path)
        self._mapping_path = Path(mapping_path)
        self._width = int(width)
        self._height = int(height)
        self._rt_subframes = int(rt_subframes)
        self._save_runtime_ids = bool(save_runtime_ids)
        self._strict_mapping = bool(strict_mapping)
        self._render_product = None
        self._writer: SemanticDatasetWriter | None = None
        self._backend = None
        self._state = CameraSchedulerState.CREATED
        self.camera_path = ""

    @property
    def state(self) -> CameraSchedulerState:
        return self._state

    def _require_state(self, *states: CameraSchedulerState) -> None:
        if self._state not in states:
            expected = ", ".join(state.name for state in states)
            raise RuntimeError(
                f"SemanticCameraScheduler state is {self._state.name}; expected {expected}"
            )

    def _resolve_camera_path(self) -> str:
        if not self._requested_camera_path or not self._requested_camera_path.startswith("/"):
            raise RuntimeError("Camera prim path must be a non-empty absolute path")
        prim = self._stage.GetPrimAtPath(self._requested_camera_path)
        if not prim.IsValid() or not prim.IsA(UsdGeom.Camera):
            raise RuntimeError(f"Camera prim is missing or invalid: {self._requested_camera_path}")
        return str(prim.GetPath())

    def initialize(self) -> None:
        """Resolve the Camera and create one RenderProduct for the entire run."""
        self._require_state(CameraSchedulerState.CREATED)
        self.camera_path = self._resolve_camera_path()
        semantic_prim_count = sum(
            any(str(schema).startswith("SemanticsLabelsAPI") for schema in prim.GetAppliedSchemas())
            for prim in self._stage.Traverse()
        )
        if semantic_prim_count == 0:
            raise RuntimeError("No SemanticsLabelsAPI labels were found in the stage")

        rep.orchestrator.set_capture_on_play(False)
        self._render_product = rep.create.render_product(
            self.camera_path,
            resolution=(self._width, self._height),
            name="SemanticCapture",
        )
        self._render_product.hydra_texture.set_updates_enabled(True)
        self._state = CameraSchedulerState.RENDER_PRODUCT_READY
        print(
            f"[semantic-camera] Persistent RenderProduct created: camera={self.camera_path}, "
            f"resolution={self._width}x{self._height}, semantic prims={semantic_prim_count}"
        )

    def warmup(self, render_frame_count: int) -> None:
        self._require_state(CameraSchedulerState.RENDER_PRODUCT_READY)
        if render_frame_count < 0:
            raise ValueError("render_frame_count must be non-negative")
        for _ in range(render_frame_count):
            self._app.update()
        # Do not disable Hydra updates here. The same RenderProduct and temporal
        # history must survive from warm-up through the final capture frame.
        self._state = CameraSchedulerState.WARMED
        print(f"[semantic-camera] Render warmup complete: frames={render_frame_count}")

    def attach_writer(self) -> None:
        self._require_state(CameraSchedulerState.WARMED)
        if self._render_product is None:
            raise RuntimeError("RenderProduct is missing before Writer attach")
        self._backend = DiskBackend(output_dir=str(self._output_path), overwrite=True)
        self._writer = SemanticDatasetWriter(
            backend=self._backend,
            semantic_schema=str(self._mapping_path),
            rgb=True,
            save_runtime_ids=self._save_runtime_ids,
            strict_mapping=self._strict_mapping,
        )
        self._writer.attach(self._render_product)
        self._state = CameraSchedulerState.WRITER_ATTACHED
        print("[semantic-camera] Writer attached after warmup")

    def capture(self, context: CaptureContext) -> CaptureReceipt:
        self._require_state(
            CameraSchedulerState.WRITER_ATTACHED,
            CameraSchedulerState.CAPTURING,
        )
        if self._render_product is None or self._writer is None:
            raise RuntimeError("SemanticCameraScheduler is not fully initialized")
        if context.camera_path != self.camera_path:
            raise RuntimeError(
                f"CaptureContext camera {context.camera_path} does not match {self.camera_path}"
            )
        self._writer.arm_capture(context)
        rep.orchestrator.step(
            rt_subframes=self._rt_subframes,
            delta_time=0.0,
            pause_timeline=False,
        )
        # Blocking frame synchronization is deliberate in the correctness-first
        # implementation. Queued/asynchronous capture can be added after parity.
        rep.orchestrator.wait_until_complete()
        receipt = self._writer.require_completed(context.frame_id)
        self._state = CameraSchedulerState.CAPTURING
        return receipt

    def wait_until_complete(self) -> None:
        rep.orchestrator.wait_until_complete()
        if self._writer is not None and self._writer.pending_count:
            raise RuntimeError(
                f"Writer still has {self._writer.pending_count} pending CaptureContext(s)"
            )

    def get_state(self) -> dict[str, Any]:
        prim = self._stage.GetPrimAtPath(self.camera_path)
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        matrix = cache.GetLocalToWorldTransform(prim)
        camera = UsdGeom.Camera(prim)
        optics: dict[str, Any] = {}
        for name, getter_name in (
            ("projection", "GetProjectionAttr"),
            ("focal_length", "GetFocalLengthAttr"),
            ("horizontal_aperture", "GetHorizontalApertureAttr"),
            ("vertical_aperture", "GetVerticalApertureAttr"),
            ("clipping_range", "GetClippingRangeAttr"),
            ("focus_distance", "GetFocusDistanceAttr"),
            ("optical_f_stop", "GetFStopAttr"),
            ("shutter_open", "GetShutterOpenAttr"),
            ("shutter_close", "GetShutterCloseAttr"),
        ):
            getter = getattr(camera, getter_name, None)
            if getter is not None:
                optics[name] = _usd_value(getter().Get())
        for attribute_name in ("exposure:fStop", "exposure:time", "exposure:iso"):
            attribute = prim.GetAttribute(attribute_name)
            if attribute and attribute.IsValid() and attribute.HasAuthoredValueOpinion():
                optics[attribute_name] = _usd_value(attribute.Get())
        return {
            "path": self.camera_path,
            "world_transform": [
                float(matrix[row][column]) for row in range(4) for column in range(4)
            ],
            "optics": optics,
        }

    def statistics(self) -> dict[str, int]:
        return {
            "pending": self._writer.pending_count if self._writer is not None else 0,
            "completed": self._writer.completed_count if self._writer is not None else 0,
        }

    def close(self) -> None:
        if self._state is CameraSchedulerState.CLOSED:
            return
        if self._writer is not None:
            self._writer.detach()
            self._writer = None
        if self._render_product is not None:
            self._render_product.destroy()
            self._render_product = None
        self._state = CameraSchedulerState.CLOSED
