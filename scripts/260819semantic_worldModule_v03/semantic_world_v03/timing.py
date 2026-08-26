"""Integer-step timing for deterministic multi-rate sensor scheduling."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import RunConfig, SensorConfig
from .errors import ConfigurationError


def _integer_steps(seconds: float, physics_hz: int, label: str) -> int:
    value = seconds * physics_hz
    rounded = round(value)
    if not math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise ConfigurationError(f"{label} must align to a physics step")
    return int(rounded)


@dataclass(frozen=True)
class SensorDue:
    sensor_id: str
    sample_id: int
    physics_step: int
    dataset_time: float
    interval_start: float | None
    interval_end: float | None


@dataclass(frozen=True)
class SensorSchedule:
    sensor: SensorConfig
    physics_hz: int
    period_steps: int
    phase_steps: int

    @classmethod
    def build(cls, sensor: SensorConfig, physics_hz: int) -> "SensorSchedule":
        period_steps = _integer_steps(
            1.0 / sensor.clock.hz, physics_hz, f"sensor {sensor.sensor_id} period"
        )
        phase_steps = _integer_steps(
            sensor.clock.phase_seconds, physics_hz, f"sensor {sensor.sensor_id} phase_seconds"
        )
        if sensor.clock.acquisition.value == "interval":
            phase_steps = max(phase_steps, period_steps)
        return cls(sensor, physics_hz, period_steps, phase_steps)

    def due_at(self, physics_step: int) -> SensorDue | None:
        if physics_step < self.phase_steps:
            return None
        offset = physics_step - self.phase_steps
        if offset % self.period_steps:
            return None
        sample_id = offset // self.period_steps
        end = physics_step / self.physics_hz
        start: float | None = None
        if self.sensor.clock.acquisition.value == "interval":
            start = max(0.0, end - self.period_steps / self.physics_hz)
        return SensorDue(
            sensor_id=self.sensor.sensor_id,
            sample_id=sample_id,
            physics_step=physics_step,
            dataset_time=end,
            interval_start=start,
            interval_end=end if start is not None else None,
        )


class CaptureTimeline:
    """Maps dataset frame IDs to exact physics steps without float accumulation."""

    def __init__(self, config: RunConfig) -> None:
        self.physics_hz = config.scene.physics_hz
        self.base_steps = _integer_steps(
            1.0 / config.capture.base_hz, self.physics_hz, "capture.base_hz period"
        )
        self.capture_initial_frame = config.capture.capture_initial_frame
        self.schedules = {
            sensor.sensor_id: SensorSchedule.build(sensor, self.physics_hz)
            for sensor in config.enabled_sensors
        }

    def physics_step_for_frame(self, frame_id: int) -> int:
        if frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        ordinal = frame_id if self.capture_initial_frame else frame_id + 1
        return ordinal * self.base_steps

    def due_for_frame(self, frame_id: int) -> tuple[SensorDue, ...]:
        step = self.physics_step_for_frame(frame_id)
        return tuple(
            due
            for schedule in self.schedules.values()
            if (due := schedule.due_at(step)) is not None
        )
