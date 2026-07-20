"""Immutable frame context shared by the capture scheduler and Writer."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
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

    def __post_init__(self) -> None:
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
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
        self._completed: dict[int, CaptureReceipt] = {}
        self._lock = threading.Lock()

    def arm(self, context: CaptureContext) -> None:
        with self._lock:
            if context.frame_id in self._completed or any(
                item.frame_id == context.frame_id for item in self._pending
            ):
                raise RuntimeError(f"Capture frame {context.frame_id} was armed more than once")
            self._pending.append(context)

    def consume(self) -> CaptureContext:
        with self._lock:
            if not self._pending:
                raise RuntimeError("Writer received data without an armed CaptureContext")
            return self._pending.popleft()

    def complete(self, receipt: CaptureReceipt) -> None:
        with self._lock:
            if receipt.frame_id in self._completed:
                raise RuntimeError(f"Capture frame {receipt.frame_id} completed more than once")
            self._completed[receipt.frame_id] = receipt

    def require_completed(self, frame_id: int) -> CaptureReceipt:
        with self._lock:
            receipt = self._completed.get(frame_id)
        if receipt is None:
            raise RuntimeError(f"Writer did not complete capture frame {frame_id}")
        return receipt

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def completed_count(self) -> int:
        with self._lock:
            return len(self._completed)
