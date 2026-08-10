"""Pure coordination logic for direct-position motion and actual-angle recording."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .config import ProjectConfig
from .motion_planner import ConstantSpeedPlanner
from .root_motion import (
    euler_xyz_degrees_from_quaternion_wxyz,
    integrate_planar_root_pose,
    normalize_quaternion_wxyz,
)
from .trajectory_recorder import ActualAngleRecorder


ROOT_ORIENTATION_COLUMNS = (
    "root_quat_w",
    "root_quat_x",
    "root_quat_y",
    "root_quat_z",
    "root_roll_x_deg",
    "root_pitch_y_deg",
    "root_yaw_z_deg",
)
ROOT_WORLD_POSITION_COLUMNS = (
    "root_world_x_m",
    "root_world_y_m",
    "root_world_z_m",
)
ROOT_POSE_COLUMNS = (*ROOT_ORIENTATION_COLUMNS, *ROOT_WORLD_POSITION_COLUMNS)


class PositionAdapter(Protocol):
    @property
    def ready(self) -> bool: ...

    def get_positions_degrees(self) -> tuple[float, ...]: ...

    def set_positions_degrees(self, positions_degrees: Sequence[float]) -> None: ...

    def hold_current_position(self) -> tuple[float, ...]: ...

    def get_root_world_pose(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]: ...

    def set_root_world_pose(
        self,
        position_meters: Sequence[float],
        orientation_wxyz: Sequence[float],
    ) -> None: ...


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
    root_position_meters: tuple[float, float, float] | None
    root_orientation_wxyz: tuple[float, float, float, float] | None
    root_forward_axis: float
    root_turn_axis: float
    root_vertical_axis: float


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
        self._root_position: tuple[float, float, float] | None = None
        self._root_orientation: tuple[float, float, float, float] | None = None
        self._root_forward_axis = 0.0
        self._root_turn_axis = 0.0
        self._root_vertical_axis = 0.0
        self._root_linear_speed = config.root_motion.linear_speed_meters_per_second
        self._root_vertical_speed = config.root_motion.vertical_speed_meters_per_second
        self._root_angular_speed = config.root_motion.angular_speed_degrees_per_second

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
        self._synchronize_root_pose()
        self.state = MotionState.IDLE
        return self.snapshot()

    def set_root_motion_input(
        self, forward_axis: float, turn_axis: float, vertical_axis: float = 0.0
    ) -> ControllerSnapshot:
        """Set normalized WASD+FG axes without interrupting joint target motion."""

        self._require_synchronized()
        if not self.config.root_motion.enabled:
            raise RuntimeError("Root motion is disabled in the active profile")
        forward = float(forward_axis)
        turn = float(turn_axis)
        vertical = float(vertical_axis)
        if not math.isfinite(forward) or not -1.0 <= forward <= 1.0:
            raise ValueError("forward_axis must be finite and inside [-1, 1]")
        if not math.isfinite(turn) or not -1.0 <= turn <= 1.0:
            raise ValueError("turn_axis must be finite and inside [-1, 1]")
        if not math.isfinite(vertical) or not -1.0 <= vertical <= 1.0:
            raise ValueError("vertical_axis must be finite and inside [-1, 1]")
        self._root_forward_axis = forward
        self._root_turn_axis = turn
        self._root_vertical_axis = vertical
        return self.snapshot()

    def stop_root_motion(self) -> ControllerSnapshot:
        """Clear root motion commands while leaving joint motion untouched."""

        self._require_synchronized()
        self._root_forward_axis = 0.0
        self._root_turn_axis = 0.0
        self._root_vertical_axis = 0.0
        self._synchronize_root_pose()
        if self.config.root_motion.enabled and self._root_position and self._root_orientation:
            self.adapter.set_root_world_pose(self._root_position, self._root_orientation)
        return self.snapshot()

    def set_root_motion_speeds(
        self,
        linear_speed_meters_per_second: float,
        angular_speed_degrees_per_second: float,
        vertical_speed_meters_per_second: float | None = None,
    ) -> None:
        """Update live GUI speed settings without mutating the loaded profile."""

        self._require_synchronized()
        linear = float(linear_speed_meters_per_second)
        angular = float(angular_speed_degrees_per_second)
        vertical = (
            self._root_vertical_speed
            if vertical_speed_meters_per_second is None
            else float(vertical_speed_meters_per_second)
        )
        if not math.isfinite(linear) or linear <= 0:
            raise ValueError("Root linear speed must be positive and finite")
        if not math.isfinite(angular) or angular <= 0:
            raise ValueError("Root angular speed must be positive and finite")
        if not math.isfinite(vertical) or vertical <= 0:
            raise ValueError("Root vertical speed must be positive and finite")
        self._root_linear_speed = linear
        self._root_angular_speed = angular
        self._root_vertical_speed = vertical

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

        if self.config.root_motion.enabled:
            self._synchronize_root_pose()
            if (
                self.state is not MotionState.ERROR
                and (
                    self._root_forward_axis != 0.0
                    or self._root_turn_axis != 0.0
                    or self._root_vertical_axis != 0.0
                )
            ):
                assert self._root_position is not None
                assert self._root_orientation is not None
                root_pose = integrate_planar_root_pose(
                    self._root_position,
                    self._root_orientation,
                    self._root_forward_axis,
                    self._root_turn_axis,
                    self._root_linear_speed,
                    self._root_angular_speed,
                    dt_value,
                    vertical_axis=self._root_vertical_axis,
                    vertical_speed_meters_per_second=self._root_vertical_speed,
                )
                self.adapter.set_root_world_pose(
                    root_pose.position_meters,
                    root_pose.orientation_wxyz,
                )
                self._synchronize_root_pose()

        if self.recording:
            self._record_elapsed += dt_value
            self._recorder.record(
                self._record_elapsed,
                self._ordered(self._current),
                self._root_pose_record_values(),
            )
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
        if self.config.root_motion.enabled:
            self._synchronize_root_pose()
        additional_columns = ROOT_POSE_COLUMNS if self.config.root_motion.enabled else ()
        recorder = ActualAngleRecorder(
            output_path,
            self.joint_names,
            additional_columns=additional_columns,
        )
        recording_metadata = dict(metadata)
        recording_metadata.setdefault(
            "column_descriptions",
            self._column_descriptions(additional_columns),
        )
        if self.config.root_motion.enabled:
            recording_metadata.setdefault(
                "world_position_reference",
                {
                    "type": "model_origin",
                    "prim_path": self.config.articulation_root_path,
                    "description": (
                        "root_world_x_m/y_m/z_m are the world coordinates of the "
                        "excavator model origin represented by the Articulation Root"
                    ),
                    "unit": "meter",
                    "axis_convention": "Isaac Sim world X/Y/Z",
                },
            )
        recorder.start(
            self._ordered(self._current),
            recording_metadata,
            initial_additional_values=self._root_pose_record_values(),
        )
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
        self._root_forward_axis = 0.0
        self._root_turn_axis = 0.0
        self._root_vertical_axis = 0.0
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
            root_position_meters=self._root_position,
            root_orientation_wxyz=self._root_orientation,
            root_forward_axis=self._root_forward_axis,
            root_turn_axis=self._root_turn_axis,
            root_vertical_axis=self._root_vertical_axis,
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

    def _synchronize_root_pose(self) -> None:
        if not self.config.root_motion.enabled:
            self._root_position = None
            self._root_orientation = None
            return
        position, orientation = self.adapter.get_root_world_pose()
        self._root_position = tuple(float(value) for value in position)
        self._root_orientation = tuple(float(value) for value in orientation)

    def _root_orientation_record_values(self) -> tuple[float, ...]:
        if not self.config.root_motion.enabled:
            return ()
        if self._root_orientation is None:
            raise RuntimeError("Root orientation is unavailable for recording")
        quaternion = normalize_quaternion_wxyz(self._root_orientation)
        euler = euler_xyz_degrees_from_quaternion_wxyz(quaternion)
        return (*quaternion, *euler)

    def _root_pose_record_values(self) -> tuple[float, ...]:
        if not self.config.root_motion.enabled:
            return ()
        if self._root_position is None:
            raise RuntimeError("Root position is unavailable for recording")
        return (*self._root_orientation_record_values(), *self._root_position)

    def _column_descriptions(
        self, additional_columns: Sequence[str]
    ) -> dict[str, str]:
        descriptions = {
            "time": "采样时间，单位秒（s）；从开始记录时刻累计",
        }
        joint_display_names = {
            joint.logical_name: joint.display_name for joint in self.config.joints
        }
        for joint_name in self.joint_names:
            display_name = joint_display_names.get(joint_name, joint_name)
            descriptions[joint_name] = (
                f"{display_name}关节的实际角度，单位度（deg）；顺序与配置文件 joints 一致"
            )
        descriptions.update(
            {
                "root_quat_w": "挖机模型原点的 Root 世界旋转四元数 w 分量；无量纲，四元数顺序为 wxyz",
                "root_quat_x": "挖机模型原点的 Root 世界旋转四元数 x 分量；无量纲，四元数顺序为 wxyz",
                "root_quat_y": "挖机模型原点的 Root 世界旋转四元数 y 分量；无量纲，四元数顺序为 wxyz",
                "root_quat_z": "挖机模型原点的 Root 世界旋转四元数 z 分量；无量纲，四元数顺序为 wxyz",
                "root_roll_x_deg": "Root 绕约定 X 轴的滚转角；单位度（deg）",
                "root_pitch_y_deg": "Root 绕约定 Y 轴的俯仰角；单位度（deg）",
                "root_yaw_z_deg": "Root 绕约定 Z 轴的偏航角；单位度（deg）",
                "root_world_x_m": "挖机模型原点（Articulation Root）的世界坐标 X；单位米（m）",
                "root_world_y_m": "挖机模型原点（Articulation Root）的世界坐标 Y；单位米（m）",
                "root_world_z_m": "挖机模型原点（Articulation Root）的世界坐标 Z；单位米（m）",
            }
        )
        return {
            name: descriptions[name]
            for name in ("time", *self.joint_names, *additional_columns)
        }
