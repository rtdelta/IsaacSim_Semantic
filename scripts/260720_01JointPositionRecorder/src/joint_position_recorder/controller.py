"""Pure coordination logic for direct-position motion and actual-angle recording."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .config import ProjectConfig
from .motion_planner import ConstantSpeedPlanner
from .trajectory_recorder import ActualAngleRecorder


class PositionAdapter(Protocol):
    @property
    def ready(self) -> bool: ...

    def get_positions_degrees(self) -> tuple[float, ...]: ...

    def set_positions_degrees(self, positions_degrees: Sequence[float]) -> None: ...

    def hold_current_position(self) -> tuple[float, ...]: ...


class MotionState(str, Enum):
    UNBOUND = "UNBOUND"
    IDLE = "IDLE"
    MOVING = "MOVING"
    REACHED = "REACHED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ControllerSnapshot:
    state: MotionState
    current_degrees: Mapping[str, float]
    target_degrees: Mapping[str, float]
    speed_degrees_per_second: Mapping[str, float]
    joint_reached: Mapping[str, bool]
    recording: bool
    recorded_samples: int


class MotionController:
    """Drive a position adapter using deterministic constant-speed increments."""

    def __init__(
        self,
        config: ProjectConfig,
        adapter: PositionAdapter,
        limits_degrees: Mapping[str, tuple[float, float]],
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.joint_names = config.logical_joint_names
        self.limits_degrees = dict(limits_degrees)
        if set(self.limits_degrees) != set(self.joint_names):
            raise ValueError("limits_degrees must contain every configured logical joint")
        self.planner = ConstantSpeedPlanner(config.arrival_tolerance_degrees)
        self.state = MotionState.UNBOUND
        self._current = {name: 0.0 for name in self.joint_names}
        self._targets = {joint.logical_name: joint.home_degrees for joint in config.joints}
        self._speeds = {
            joint.logical_name: joint.default_speed_degrees for joint in config.joints
        }
        self._reached = {name: False for name in self.joint_names}
        self._recorder: ActualAngleRecorder | None = None
        self._record_elapsed = 0.0

    @property
    def synchronized(self) -> bool:
        return self.state is not MotionState.UNBOUND

    @property
    def recording(self) -> bool:
        return self._recorder is not None and self._recorder.active

    def synchronize(self) -> ControllerSnapshot:
        if not self.adapter.ready:
            raise RuntimeError("Articulation adapter is not ready")
        values = self.adapter.get_positions_degrees()
        self._set_current(values)
        self._targets = dict(self._current)
        self._reached = {name: True for name in self.joint_names}
        self.state = MotionState.IDLE
        return self.snapshot()

    def set_targets_and_speeds(
        self,
        targets_degrees: Mapping[str, float],
        speeds_degrees_per_second: Mapping[str, float],
    ) -> None:
        self._require_synchronized()
        if set(targets_degrees) != set(self.joint_names):
            raise ValueError(f"Targets must contain exactly {self.joint_names}")
        if set(speeds_degrees_per_second) != set(self.joint_names):
            raise ValueError(f"Speeds must contain exactly {self.joint_names}")
        validated_targets: dict[str, float] = {}
        validated_speeds: dict[str, float] = {}
        for name in self.joint_names:
            target = float(targets_degrees[name])
            speed = float(speeds_degrees_per_second[name])
            lower, upper = self.limits_degrees[name]
            if not math.isfinite(target) or not lower <= target <= upper:
                raise ValueError(
                    f"{name} target {target} is outside safe range [{lower}, {upper}] degrees"
                )
            if not math.isfinite(speed) or speed <= 0:
                raise ValueError(f"{name} speed must be positive and finite")
            validated_targets[name] = target
            validated_speeds[name] = speed
        self._targets = validated_targets
        self._speeds = validated_speeds

    def start_motion(
        self,
        targets_degrees: Mapping[str, float],
        speeds_degrees_per_second: Mapping[str, float],
    ) -> ControllerSnapshot:
        self.set_targets_and_speeds(targets_degrees, speeds_degrees_per_second)
        self._set_current(self.adapter.get_positions_degrees())
        self._reached = {
            name: abs(self._targets[name] - self._current[name])
            <= self.config.arrival_tolerance_degrees
            for name in self.joint_names
        }
        self.state = MotionState.REACHED if all(self._reached.values()) else MotionState.MOVING
        return self.snapshot()

    def update(self, dt: float) -> ControllerSnapshot:
        self._require_synchronized()
        dt_value = float(dt)
        if not math.isfinite(dt_value) or dt_value <= 0:
            return self.snapshot()
        dt_value = min(dt_value, self.config.max_update_dt)
        self._set_current(self.adapter.get_positions_degrees())

        if self.state is MotionState.MOVING:
            result = self.planner.step(
                self._ordered(self._current),
                self._ordered(self._targets),
                self._ordered(self._speeds),
                dt_value,
            )
            self.adapter.set_positions_degrees(result.positions_degrees)
            self._set_current(self.adapter.get_positions_degrees())
            self._reached = {
                name: abs(self._targets[name] - self._current[name])
                <= self.config.arrival_tolerance_degrees
                for name in self.joint_names
            }
            if all(self._reached.values()):
                final_positions = self._ordered(self._targets)
                self.adapter.set_positions_degrees(final_positions)
                self._set_current(self.adapter.get_positions_degrees())
                self._reached = {name: True for name in self.joint_names}
                self.state = MotionState.REACHED

        if self.recording:
            self._record_elapsed += dt_value
            self._recorder.record(self._record_elapsed, self._ordered(self._current))
        return self.snapshot()

    def stop_motion(self) -> ControllerSnapshot:
        self._require_synchronized()
        current = self.adapter.hold_current_position()
        self._set_current(current)
        self._targets = dict(self._current)
        self._reached = {name: True for name in self.joint_names}
        self.state = MotionState.IDLE
        return self.snapshot()

    def reset_targets_to_current(self) -> ControllerSnapshot:
        self._require_synchronized()
        self._set_current(self.adapter.get_positions_degrees())
        self._targets = dict(self._current)
        self._reached = {name: True for name in self.joint_names}
        if self.state is not MotionState.ERROR:
            self.state = MotionState.IDLE
        return self.snapshot()

    def start_home_motion(self) -> ControllerSnapshot:
        targets = {joint.logical_name: joint.home_degrees for joint in self.config.joints}
        return self.start_motion(targets, self._speeds)

    def start_recording(self, output_path: str | Path, metadata: Mapping[str, Any]) -> Path:
        self._require_synchronized()
        if self.recording:
            raise RuntimeError("Recording is already active")
        self._set_current(self.adapter.get_positions_degrees())
        recorder = ActualAngleRecorder(output_path, self.joint_names)
        recorder.start(self._ordered(self._current), metadata)
        self._recorder = recorder
        self._record_elapsed = 0.0
        return recorder.partial_path

    def stop_recording(self, metadata: Mapping[str, Any] | None = None) -> Path:
        if not self.recording or self._recorder is None:
            raise RuntimeError("Recording is not active")
        output = self._recorder.stop(metadata)
        self._recorder = None
        return output

    def abort_recording(self) -> Path | None:
        if self._recorder is None:
            return None
        output = self._recorder.abort()
        self._recorder = None
        return output

    def fail(self) -> None:
        self.state = MotionState.ERROR
        self.abort_recording()

    def snapshot(self) -> ControllerSnapshot:
        return ControllerSnapshot(
            state=self.state,
            current_degrees=dict(self._current),
            target_degrees=dict(self._targets),
            speed_degrees_per_second=dict(self._speeds),
            joint_reached=dict(self._reached),
            recording=self.recording,
            recorded_samples=self._recorder.sample_count if self._recorder is not None else 0,
        )

    def _require_synchronized(self) -> None:
        if not self.synchronized:
            raise RuntimeError("Controller is not synchronized with an articulation")
        if not self.adapter.ready:
            raise RuntimeError("Articulation adapter is not ready")

    def _ordered(self, values: Mapping[str, float]) -> tuple[float, ...]:
        return tuple(float(values[name]) for name in self.joint_names)

    def _set_current(self, values: Sequence[float]) -> None:
        positions = tuple(float(value) for value in values)
        if len(positions) != len(self.joint_names):
            raise RuntimeError(
                f"Expected {len(self.joint_names)} articulation positions, got {len(positions)}"
            )
        if any(not math.isfinite(value) for value in positions):
            raise RuntimeError("Articulation returned a non-finite joint position")
        self._current = dict(zip(self.joint_names, positions))
