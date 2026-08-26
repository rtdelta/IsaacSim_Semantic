"""Immutable frame context shared by the capture scheduler and Writer."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


def _jsonable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a nested mapping into JSON-friendly builtin containers."""
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            result[str(key)] = _jsonable_mapping(item)
        elif isinstance(item, tuple):
            result[str(key)] = list(item)
        elif isinstance(item, list):
            result[str(key)] = list(item)
        else:
            result[str(key)] = item
    return result


class CaptureVariant(str, Enum):
    """Render-scene variant produced for one authoritative simulation frame."""

    FULL_SCENE = "full_scene"
    EXCAVATOR_ONLY = "excavator_only"
    FRONT_TEETH_ONLY = "front_teeth_only"


class CaptureOperation(str, Enum):
    """How one RenderProduct result is consumed by the dataset Writer."""

    PROBE = "probe"
    CAPTURE = "capture"


@dataclass(frozen=True)
class FrozenWorldSnapshot:
    """World timing values that must not change while one image is rendered."""

    physics_step: int
    dataset_time: float
    timeline_time: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "physics_step": int(self.physics_step),
            "dataset_time": float(self.dataset_time),
            "timeline_time": float(self.timeline_time),
        }


@dataclass(frozen=True)
class CaptureContext:
    """Authoritative identity and scene state for one requested output frame."""

    frame_id: int
    dataset_time: float
    timeline_time: float
    physics_step: int
    camera_path: str
    camera_world_transform: tuple[float, ...]
    motion_state: Mapping[str, Any]
    variant: CaptureVariant = CaptureVariant.FULL_SCENE
    operation: CaptureOperation = CaptureOperation.CAPTURE
    visibility_generation: int = 0
    attempt: int = 0
    probe_index: int = 0
    settle_attempts_before_capture: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.variant, CaptureVariant):
            try:
                object.__setattr__(self, "variant", CaptureVariant(self.variant))
            except ValueError as exc:
                raise ValueError(f"Unsupported capture variant: {self.variant!r}") from exc
        if not isinstance(self.operation, CaptureOperation):
            try:
                object.__setattr__(self, "operation", CaptureOperation(self.operation))
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported capture operation: {self.operation!r}"
                ) from exc
        if self.frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        if self.dataset_time < 0:
            raise ValueError("dataset_time must be non-negative")
        if self.physics_step < 0:
            raise ValueError("physics_step must be non-negative")
        if self.visibility_generation < 0:
            raise ValueError("visibility_generation must be non-negative")
        if self.attempt < 0:
            raise ValueError("attempt must be non-negative")
        if self.probe_index < 0:
            raise ValueError("probe_index must be non-negative")
        if self.settle_attempts_before_capture < 0:
            raise ValueError("settle_attempts_before_capture must be non-negative")
        if self.operation is CaptureOperation.CAPTURE and (
            self.attempt != 0 or self.probe_index != 0
        ):
            raise ValueError("CAPTURE contexts must use attempt=0 and probe_index=0")
        if self.operation is CaptureOperation.PROBE and self.attempt < 1:
            raise ValueError("PROBE contexts must use attempt greater than or equal to 1")
        if not self.camera_path:
            raise ValueError("camera_path must not be empty")
        if len(self.camera_world_transform) != 16:
            raise ValueError("camera_world_transform must contain 16 values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
            "capture_operation": self.operation.value,
            "capture_variant": self.variant.value,
            "visibility_generation": int(self.visibility_generation),
            "attempt": int(self.attempt),
            "probe_index": int(self.probe_index),
            "settle_attempts_before_capture": int(
                self.settle_attempts_before_capture
            ),
            "dataset_time": float(self.dataset_time),
            "timeline_time": float(self.timeline_time),
            "physics_step": int(self.physics_step),
            "camera": {
                "path": self.camera_path,
                "world_transform": [float(value) for value in self.camera_world_transform],
            },
            "motion": _jsonable_mapping(self.motion_state),
        }


@dataclass(frozen=True)
class CaptureReceipt:
    """Relative paths scheduled by the Writer for one completed frame."""

    frame_id: int
    rgb_path: str | None
    semantic_id_path: str
    semantic_color_path: str
    runtime_id_path: str | None
    metadata_path: str
    variant: CaptureVariant = CaptureVariant.FULL_SCENE
    visibility_generation: int = 0
    semantic_labels_present: tuple[str, ...] = ()
    validation_passed: bool = True
    validation_errors: tuple[str, ...] = ()
    staged_files: tuple[tuple[str, str], ...] = ()
    settle_attempts_before_capture: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.variant, CaptureVariant):
            try:
                object.__setattr__(self, "variant", CaptureVariant(self.variant))
            except ValueError as exc:
                raise ValueError(f"Unsupported capture variant: {self.variant!r}") from exc
        if self.frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        if self.visibility_generation < 0:
            raise ValueError("visibility_generation must be non-negative")
        if not self.validation_passed:
            raise ValueError("A failed validation cannot produce a CaptureReceipt")
        if self.settle_attempts_before_capture < 0:
            raise ValueError("settle_attempts_before_capture must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
            "capture_operation": CaptureOperation.CAPTURE.value,
            "capture_variant": self.variant.value,
            "visibility_generation": int(self.visibility_generation),
            "rgb": self.rgb_path,
            "semantic_id": self.semantic_id_path,
            "semantic_color": self.semantic_color_path,
            "semantic_runtime_id": self.runtime_id_path,
            "metadata": self.metadata_path,
            "semantic_labels_present": list(self.semantic_labels_present),
            "validation_passed": bool(self.validation_passed),
            "validation_errors": list(self.validation_errors),
            "settle_attempts_before_capture": int(
                self.settle_attempts_before_capture
            ),
            "staged_files": [
                {"staged": staged, "final": final}
                for staged, final in self.staged_files
            ],
        }


@dataclass(frozen=True)
class ProbeReceipt:
    """Validation-only result that must never publish dataset files."""

    frame_id: int
    variant: CaptureVariant
    visibility_generation: int
    attempt: int
    probe_index: int
    resolution: tuple[int, int]
    semantic_labels_present: tuple[str, ...]
    semantic_dataset_ids_present: tuple[int, ...]
    validation_passed: bool
    validation_errors: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.variant, CaptureVariant):
            try:
                object.__setattr__(self, "variant", CaptureVariant(self.variant))
            except ValueError as exc:
                raise ValueError(f"Unsupported capture variant: {self.variant!r}") from exc
        if self.frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        if self.visibility_generation < 0:
            raise ValueError("visibility_generation must be non-negative")
        if self.attempt < 1:
            raise ValueError("attempt must be greater than or equal to 1")
        if self.probe_index < 0:
            raise ValueError("probe_index must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
            "capture_operation": CaptureOperation.PROBE.value,
            "capture_variant": self.variant.value,
            "visibility_generation": int(self.visibility_generation),
            "attempt": int(self.attempt),
            "probe_index": int(self.probe_index),
            "resolution": [int(value) for value in self.resolution],
            "semantic_labels_present": list(self.semantic_labels_present),
            "semantic_dataset_ids_present": [
                int(value) for value in self.semantic_dataset_ids_present
            ],
            "validation_passed": bool(self.validation_passed),
            "validation_errors": list(self.validation_errors),
        }


class CaptureLedger:
    """Thread-safe FIFO that binds Writer callbacks to requested frame contexts."""

    def __init__(self) -> None:
        self._pending: deque[CaptureContext] = deque()
        self._completed: dict[tuple[int, CaptureVariant], CaptureReceipt] = {}
        self._completed_probes: dict[
            tuple[int, CaptureVariant, int, int, int], ProbeReceipt
        ] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(frame_id: int, variant: CaptureVariant) -> tuple[int, CaptureVariant]:
        return int(frame_id), CaptureVariant(variant)

    def arm(self, context: CaptureContext) -> None:
        with self._lock:
            if context.operation is CaptureOperation.CAPTURE:
                key = self._key(context.frame_id, context.variant)
                duplicate = key in self._completed or any(
                    item.operation is CaptureOperation.CAPTURE
                    and self._key(item.frame_id, item.variant) == key
                    for item in self._pending
                )
                identity = f"capture {context.frame_id}/{context.variant.value}"
            else:
                probe_key = self._probe_key(context)
                duplicate = probe_key in self._completed_probes or any(
                    item.operation is CaptureOperation.PROBE
                    and self._probe_key(item) == probe_key
                    for item in self._pending
                )
                identity = (
                    f"probe {context.frame_id}/{context.variant.value}/"
                    f"g{context.visibility_generation}/a{context.attempt}/"
                    f"p{context.probe_index}"
                )
            if duplicate:
                raise RuntimeError(f"Render request {identity} was armed more than once")
            self._pending.append(context)

    @staticmethod
    def _probe_key(
        context: CaptureContext,
    ) -> tuple[int, CaptureVariant, int, int, int]:
        return (
            int(context.frame_id),
            CaptureVariant(context.variant),
            int(context.visibility_generation),
            int(context.attempt),
            int(context.probe_index),
        )

    def consume(self) -> CaptureContext:
        with self._lock:
            if not self._pending:
                raise RuntimeError("Writer received data without an armed CaptureContext")
            return self._pending.popleft()

    def complete(self, receipt: CaptureReceipt) -> None:
        key = self._key(receipt.frame_id, receipt.variant)
        with self._lock:
            if key in self._completed:
                raise RuntimeError(
                    f"Capture frame {receipt.frame_id}/{receipt.variant.value} "
                    "completed more than once"
                )
            self._completed[key] = receipt

    def complete_probe(self, receipt: ProbeReceipt) -> None:
        key = (
            int(receipt.frame_id),
            CaptureVariant(receipt.variant),
            int(receipt.visibility_generation),
            int(receipt.attempt),
            int(receipt.probe_index),
        )
        with self._lock:
            if key in self._completed_probes:
                raise RuntimeError(
                    f"Probe frame {receipt.frame_id}/{receipt.variant.value}/"
                    f"g{receipt.visibility_generation}/a{receipt.attempt}/"
                    f"p{receipt.probe_index} completed more than once"
                )
            self._completed_probes[key] = receipt

    def require_completed(
        self,
        frame_id: int,
        variant: CaptureVariant = CaptureVariant.FULL_SCENE,
    ) -> CaptureReceipt:
        key = self._key(frame_id, variant)
        with self._lock:
            receipt = self._completed.get(key)
        if receipt is None:
            raise RuntimeError(
                f"Writer did not complete capture frame {frame_id}/{CaptureVariant(variant).value}"
            )
        return receipt

    def require_probe_completed(self, context: CaptureContext) -> ProbeReceipt:
        if context.operation is not CaptureOperation.PROBE:
            raise ValueError("require_probe_completed expects a PROBE context")
        key = self._probe_key(context)
        with self._lock:
            receipt = self._completed_probes.get(key)
        if receipt is None:
            raise RuntimeError(
                f"Writer did not complete probe frame {context.frame_id}/"
                f"{context.variant.value}/g{context.visibility_generation}/"
                f"a{context.attempt}/p{context.probe_index}"
            )
        return receipt

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def completed_count(self) -> int:
        with self._lock:
            return len(self._completed)

    @property
    def completed_by_variant(self) -> dict[str, int]:
        with self._lock:
            return {
                variant.value: sum(
                    1 for (_frame_id, completed_variant) in self._completed
                    if completed_variant is variant
                )
                for variant in CaptureVariant
            }

    @property
    def completed_probe_count(self) -> int:
        with self._lock:
            return len(self._completed_probes)
