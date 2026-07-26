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

    def __post_init__(self) -> None:
        if not isinstance(self.variant, CaptureVariant):
            try:
                object.__setattr__(self, "variant", CaptureVariant(self.variant))
            except ValueError as exc:
                raise ValueError(f"Unsupported capture variant: {self.variant!r}") from exc
        if self.frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        if self.dataset_time < 0:
            raise ValueError("dataset_time must be non-negative")
        if self.physics_step < 0:
            raise ValueError("physics_step must be non-negative")
        if not self.camera_path:
            raise ValueError("camera_path must not be empty")
        if len(self.camera_world_transform) != 16:
            raise ValueError("camera_world_transform must contain 16 values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
            "capture_variant": self.variant.value,
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

    def __post_init__(self) -> None:
        if not isinstance(self.variant, CaptureVariant):
            try:
                object.__setattr__(self, "variant", CaptureVariant(self.variant))
            except ValueError as exc:
                raise ValueError(f"Unsupported capture variant: {self.variant!r}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
            "capture_variant": self.variant.value,
            "rgb": self.rgb_path,
            "semantic_id": self.semantic_id_path,
            "semantic_color": self.semantic_color_path,
            "semantic_runtime_id": self.runtime_id_path,
            "metadata": self.metadata_path,
        }


class CaptureLedger:
    """Thread-safe FIFO that binds Writer callbacks to requested frame contexts."""

    def __init__(self) -> None:
        self._pending: deque[CaptureContext] = deque()
        self._completed: dict[tuple[int, CaptureVariant], CaptureReceipt] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(frame_id: int, variant: CaptureVariant) -> tuple[int, CaptureVariant]:
        return int(frame_id), CaptureVariant(variant)

    def arm(self, context: CaptureContext) -> None:
        key = self._key(context.frame_id, context.variant)
        with self._lock:
            if key in self._completed or any(
                self._key(item.frame_id, item.variant) == key for item in self._pending
            ):
                raise RuntimeError(
                    f"Capture frame {context.frame_id}/{context.variant.value} "
                    "was armed more than once"
                )
            self._pending.append(context)

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
