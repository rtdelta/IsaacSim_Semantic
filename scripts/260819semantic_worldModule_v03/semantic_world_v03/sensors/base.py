"""Base lifecycle and runtime services for all sensor plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..config import SensorConfig
from ..errors import SensorStateError
from ..models import (
    CaptureRequest,
    DriverHealthState,
    PreflightReport,
    SensorCapabilities,
    SensorHealth,
    SensorLifecycle,
    SensorPacket,
)


class RenderBackend(Protocol):
    def render(self, *, rt_subframes: int) -> None: ...
    def update(self, count: int = 1) -> None: ...


@dataclass
class SensorRuntimeContext:
    simulation_app: Any
    stage: Any
    render_backend: RenderBackend
    output_root: Path
    services: dict[str, Any] = field(default_factory=dict)


class BaseSensorDriver(ABC):
    """Stateful driver with strict lifecycle checks and no core-level type branches."""

    def __init__(self, spec: SensorConfig) -> None:
        self.spec = spec
        self.sensor_id = spec.sensor_id
        self.sensor_type = spec.sensor_type
        self.lifecycle = SensorLifecycle.CREATED
        self.runtime: SensorRuntimeContext | None = None
        self.calibration: dict[str, Any] = {}
        self.calibration_hash = ""
        self._samples_captured = 0

    @property
    @abstractmethod
    def capabilities(self) -> SensorCapabilities:
        raise NotImplementedError

    def _require(self, *states: SensorLifecycle) -> None:
        if self.lifecycle not in states:
            expected = ", ".join(state.value for state in states)
            raise SensorStateError(
                f"Sensor {self.sensor_id} is {self.lifecycle.value}; expected {expected}"
            )

    def preflight(self, stage: Any) -> PreflightReport:
        self._require(SensorLifecycle.CREATED)
        report = self._preflight(stage)
        report.require_usable()
        self.lifecycle = SensorLifecycle.PREFLIGHTED
        return report

    @abstractmethod
    def _preflight(self, stage: Any) -> PreflightReport:
        raise NotImplementedError

    def initialize(self, context: SensorRuntimeContext) -> None:
        self._require(SensorLifecycle.PREFLIGHTED)
        self.runtime = context
        self._initialize(context)
        self.lifecycle = SensorLifecycle.INITIALIZED

    @abstractmethod
    def _initialize(self, context: SensorRuntimeContext) -> None:
        raise NotImplementedError

    def warmup(self) -> None:
        self._require(SensorLifecycle.INITIALIZED)
        self._warmup()
        self.lifecycle = SensorLifecycle.WARMED

    def _warmup(self) -> None:
        return None

    @abstractmethod
    def read(self, request: CaptureRequest) -> SensorPacket:
        """Read data after the coordinator/render group has triggered acquisition."""

    def capture(self, request: CaptureRequest) -> SensorPacket:
        self._require(SensorLifecycle.WARMED)
        if self.runtime is None:
            raise SensorStateError(f"Sensor {self.sensor_id} has no runtime context")
        if self.capabilities.requires_render_trigger:
            self.runtime.render_backend.render(rt_subframes=request.rt_subframes)
        packet = self.read(request)
        self._samples_captured += 1
        return packet

    def mark_sample_captured(self) -> None:
        """Used when a RenderGroup triggers once and reads several drivers."""

        self._samples_captured += 1

    def health(self) -> SensorHealth:
        if self.lifecycle is SensorLifecycle.CLOSED:
            return SensorHealth(DriverHealthState.CLOSED, metrics=self.metrics())
        state = (
            DriverHealthState.READY
            if self.lifecycle is SensorLifecycle.WARMED
            else DriverHealthState.DEGRADED
        )
        return SensorHealth(state, metrics=self.metrics())

    def metrics(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "lifecycle": self.lifecycle.value,
            "samples_captured": self._samples_captured,
        }

    def close(self) -> None:
        if self.lifecycle is SensorLifecycle.CLOSED:
            return
        try:
            self._close()
        finally:
            self.lifecycle = SensorLifecycle.CLOSED

    def _close(self) -> None:
        return None

