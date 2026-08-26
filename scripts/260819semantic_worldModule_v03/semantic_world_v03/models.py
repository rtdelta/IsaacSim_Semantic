"""Shared immutable data contracts for the v03 core and sensor plugins."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any


def jsonable(value: Any) -> Any:
    """Convert USD/NumPy-like values into deterministic JSON-compatible data."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return jsonable(value.tolist())
        except Exception:
            pass
    try:
        return [jsonable(item) for item in value]
    except TypeError:
        return str(value)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AcquisitionKind(str, Enum):
    SNAPSHOT = "snapshot"
    INTERVAL = "interval"
    CONTINUOUS = "continuous"


class SensorLifecycle(str, Enum):
    CREATED = "created"
    PREFLIGHTED = "preflighted"
    INITIALIZED = "initialized"
    WARMED = "warmed"
    CLOSED = "closed"


class DriverHealthState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass(frozen=True)
class WorldSnapshot:
    physics_step: int
    dataset_time: float
    timeline_time: float
    state: Mapping[str, Any] = field(default_factory=dict)
    state_hash: str = ""

    def __post_init__(self) -> None:
        if self.physics_step < 0:
            raise ValueError("physics_step must be non-negative")
        if not self.state_hash:
            object.__setattr__(
                self,
                "state_hash",
                stable_hash(
                    {
                        "physics_step": self.physics_step,
                        "dataset_time": self.dataset_time,
                        "state": self.state,
                    }
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "physics_step": self.physics_step,
            "dataset_time": self.dataset_time,
            "timeline_time": self.timeline_time,
            "state": jsonable(self.state),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class CaptureRequest:
    run_id: str
    capture_id: str
    frame_id: int
    sample_id: int
    sensor_id: str
    variant_id: str
    render_group: str
    snapshot: WorldSnapshot
    requested_modalities: tuple[str, ...] = ()
    rt_subframes: int = 1
    attempt: int = 1
    interval_start: float | None = None
    interval_end: float | None = None

    def __post_init__(self) -> None:
        for name in ("run_id", "capture_id", "sensor_id", "variant_id", "render_group"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        if self.frame_id < 0 or self.sample_id < 0:
            raise ValueError("frame_id and sample_id must be non-negative")
        if self.rt_subframes < 1 or self.attempt < 1:
            raise ValueError("rt_subframes and attempt must be positive")
        if any(not str(item).strip() for item in self.requested_modalities):
            raise ValueError("requested_modalities cannot contain empty names")
        if len(self.requested_modalities) != len(set(self.requested_modalities)):
            raise ValueError("requested_modalities cannot contain duplicates")
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("interval_start and interval_end must be specified together")
        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_end < self.interval_start
        ):
            raise ValueError("interval_end must be greater than or equal to interval_start")


@dataclass(frozen=True)
class SensorCapabilities:
    acquisition: AcquisitionKind
    modalities: tuple[str, ...]
    requires_render_trigger: bool
    supports_variants: bool = True


@dataclass(frozen=True)
class SensorHealth:
    state: DriverHealthState
    message: str = ""
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "message": self.message,
            "metrics": jsonable(self.metrics),
        }


@dataclass(frozen=True)
class SensorPacket:
    run_id: str
    capture_id: str
    frame_id: int
    sample_id: int
    sensor_id: str
    sensor_type: str
    variant_id: str
    acquisition: AcquisitionKind
    timestamp: float
    physics_step: int
    world_state_hash: str
    calibration_hash: str
    payloads: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    interval_start: float | None = None
    interval_end: float | None = None
    validation_passed: bool = True
    validation_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.payloads:
            raise ValueError(f"SensorPacket {self.sensor_id} has no payloads")
        if not self.validation_passed and not self.validation_errors:
            raise ValueError("A failed SensorPacket must describe validation errors")
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("Packet interval bounds must be specified together")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "capture_id": self.capture_id,
            "frame_id": self.frame_id,
            "sample_id": self.sample_id,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "variant_id": self.variant_id,
            "acquisition": self.acquisition.value,
            "timestamp": self.timestamp,
            "interval_start": self.interval_start,
            "interval_end": self.interval_end,
            "physics_step": self.physics_step,
            "world_state_hash": self.world_state_hash,
            "calibration_hash": self.calibration_hash,
            "modalities": sorted(self.payloads),
            "metadata": jsonable(self.metadata),
            "validation": {
                "passed": self.validation_passed,
                "errors": list(self.validation_errors),
            },
        }


@dataclass(frozen=True)
class PreflightIssue:
    severity: str
    code: str
    message: str
    sensor_id: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in {"warning", "error"}:
            raise ValueError(f"Unsupported issue severity: {self.severity}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "sensor_id": self.sensor_id,
        }


@dataclass(frozen=True)
class PreflightReport:
    issues: tuple[PreflightIssue, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def require_usable(self) -> None:
        if not self.usable:
            messages = "; ".join(
                issue.message for issue in self.issues if issue.severity == "error"
            )
            from .errors import PreflightError

            raise PreflightError(messages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "usable": self.usable,
            "issues": [issue.to_dict() for issue in self.issues],
            "details": jsonable(self.details),
        }
