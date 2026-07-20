"""Trajectory-file playback for the four excavator joint Drives."""

from __future__ import annotations

import bisect
import csv
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JointSpec:
    name: str
    path: str
    body_path: str


@dataclass(frozen=True)
class TrajectoryKeyframe:
    time: float
    targets: dict[str, float]


@dataclass
class JointRuntime:
    spec: JointSpec
    target_attribute: Any
    lower_limit: float
    upper_limit: float
    target: float


JOINT_SPECS = (
    JointSpec(
        name="cab",
        path="/World/Joints/track_operator_cab_joint",
        body_path="/root/Xform/operator_cab_mesh",
    ),
    JointSpec(
        name="boom",
        path="/World/Joints/platform_boom_joint",
        body_path="/root/Xform/boom_mesh",
    ),
    JointSpec(
        name="small_arm",
        path="/World/Joints/boom_small_arm_joint",
        body_path="/root/Xform/small_arm_mesh",
    ),
    JointSpec(
        name="bucket",
        path="/World/Joints/small_arm_bucket_joint",
        body_path="/root/Xform/bucket_only_full_teeth_mesh",
    ),
)
JOINT_NAMES = tuple(spec.name for spec in JOINT_SPECS)


class JointTrajectory:
    """Validated in-memory keyframes loaded from one CSV file."""

    def __init__(self, source_path: Path, keyframes: list[TrajectoryKeyframe]) -> None:
        self.source_path = Path(source_path).resolve()
        self.keyframes = keyframes
        self.times = [frame.time for frame in keyframes]
        self.duration = self.times[-1]
        self.sha256 = hashlib.sha256(self.source_path.read_bytes()).hexdigest()

    @classmethod
    def from_csv(cls, source_path: str | Path) -> "JointTrajectory":
        path = Path(source_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Trajectory CSV not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            expected_columns = ("time", *JOINT_NAMES)
            if reader.fieldnames != list(expected_columns):
                raise ValueError(
                    f"Trajectory columns must be exactly {expected_columns}, got {reader.fieldnames}"
                )
            keyframes: list[TrajectoryKeyframe] = []
            for line_number, row in enumerate(reader, start=2):
                try:
                    time_value = float(row["time"])
                    targets = {name: float(row[name]) for name in JOINT_NAMES}
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid numeric value in trajectory line {line_number}") from exc
                if not math.isfinite(time_value) or any(
                    not math.isfinite(value) for value in targets.values()
                ):
                    raise ValueError(f"Non-finite value in trajectory line {line_number}")
                keyframes.append(TrajectoryKeyframe(time=time_value, targets=targets))

        if len(keyframes) < 2:
            raise ValueError("Trajectory must contain at least two keyframes")
        if not math.isclose(keyframes[0].time, 0.0, abs_tol=1e-12):
            raise ValueError("The first trajectory keyframe must start at time 0.0")
        if any(current.time <= previous.time for previous, current in zip(keyframes, keyframes[1:])):
            raise ValueError("Trajectory times must be strictly increasing")
        return cls(path, keyframes)

    def sample(self, simulation_time: float, playback_mode: str = "loop") -> tuple[float, dict[str, float]]:
        if simulation_time < 0:
            raise ValueError("simulation_time must be non-negative")
        if playback_mode == "loop":
            trajectory_time = simulation_time % self.duration
            if simulation_time > 0 and math.isclose(trajectory_time, 0.0, abs_tol=1e-12):
                trajectory_time = self.duration
        elif playback_mode == "hold":
            trajectory_time = min(simulation_time, self.duration)
        else:
            raise ValueError(f"Unsupported trajectory playback mode: {playback_mode}")

        if trajectory_time <= self.times[0]:
            return trajectory_time, dict(self.keyframes[0].targets)
        if trajectory_time >= self.times[-1]:
            return trajectory_time, dict(self.keyframes[-1].targets)

        right = bisect.bisect_right(self.times, trajectory_time)
        left_frame = self.keyframes[right - 1]
        right_frame = self.keyframes[right]
        alpha = (trajectory_time - left_frame.time) / (right_frame.time - left_frame.time)
        targets = {
            name: left_frame.targets[name]
            + alpha * (right_frame.targets[name] - left_frame.targets[name])
            for name in JOINT_NAMES
        }
        return trajectory_time, targets


class ExcavatorJointMotion:
    """Validate and play one joint-angle CSV against the existing angular Drives."""

    def __init__(
        self,
        stage: Any,
        trajectory_path: str | Path,
        playback_mode: str = "loop",
        interpolation: str = "linear",
        safety_margin_degrees: float = 2.0,
    ) -> None:
        self._stage = stage
        self.trajectory = JointTrajectory.from_csv(trajectory_path)
        self.playback_mode = playback_mode
        self.interpolation = interpolation
        self.safety_margin_degrees = float(safety_margin_degrees)
        self._joints: dict[str, JointRuntime] = {}
        self._last_trajectory_time = 0.0

    def initialize(self) -> None:
        if self.playback_mode not in {"loop", "hold"}:
            raise ValueError("playback_mode must be 'loop' or 'hold'")
        if self.interpolation != "linear":
            raise ValueError("First-version trajectory playback supports interpolation='linear' only")

        self._joints.clear()
        for spec in JOINT_SPECS:
            prim = self._stage.GetPrimAtPath(spec.path)
            if not prim.IsValid() or prim.GetTypeName() != "PhysicsRevoluteJoint":
                raise RuntimeError(f"Missing PhysicsRevoluteJoint: {spec.path}")
            lower_attr = prim.GetAttribute("physics:lowerLimit")
            upper_attr = prim.GetAttribute("physics:upperLimit")
            target_attr = prim.GetAttribute("drive:angular:physics:targetPosition")
            if not lower_attr.IsValid() or not upper_attr.IsValid() or not target_attr.IsValid():
                raise RuntimeError(f"Joint limit or angular Drive is missing: {spec.path}")
            lower = float(lower_attr.Get())
            upper = float(upper_attr.Get())
            initial_target = float(target_attr.Get())
            runtime = JointRuntime(
                spec=spec,
                target_attribute=target_attr,
                lower_limit=lower,
                upper_limit=upper,
                target=initial_target,
            )
            self._joints[spec.name] = runtime

        for frame_index, keyframe in enumerate(self.trajectory.keyframes):
            for name, target in keyframe.targets.items():
                joint = self._joints[name]
                safe_lower = joint.lower_limit + self.safety_margin_degrees
                safe_upper = joint.upper_limit - self.safety_margin_degrees
                if not safe_lower <= target <= safe_upper:
                    raise ValueError(
                        f"Trajectory frame {frame_index} at t={keyframe.time}: {name}={target} "
                        f"is outside safe limits [{safe_lower}, {safe_upper}]"
                    )

        if self.playback_mode == "loop":
            first = self.trajectory.keyframes[0].targets
            last = self.trajectory.keyframes[-1].targets
            if any(not math.isclose(first[name], last[name], abs_tol=1e-9) for name in JOINT_NAMES):
                raise ValueError("Loop trajectory must end at the same joint targets where it starts")

        print(
            f"[excavator-motion] Loaded trajectory: {self.trajectory.source_path}, "
            f"keyframes={len(self.trajectory.keyframes)}, duration={self.trajectory.duration:.6f}s, "
            f"mode={self.playback_mode}, interpolation={self.interpolation}, "
            f"sha256={self.trajectory.sha256}"
        )
        for name in JOINT_NAMES:
            joint = self._joints[name]
            values = [frame.targets[name] for frame in self.trajectory.keyframes]
            print(
                f"[excavator-motion] {name}: trajectory=[{min(values):.6f}, {max(values):.6f}], "
                f"limits=[{joint.lower_limit:.6f}, {joint.upper_limit:.6f}]"
            )

    def update(self, simulation_time: float) -> None:
        if not self._joints:
            raise RuntimeError("ExcavatorJointMotion.initialize() must be called before update()")
        trajectory_time, targets = self.trajectory.sample(simulation_time, self.playback_mode)
        self._last_trajectory_time = trajectory_time
        for name, target in targets.items():
            joint = self._joints[name]
            joint.target = target
            joint.target_attribute.Set(target)

    def apply_initial_targets(self) -> None:
        """Author the trajectory's t=0 targets before pre-roll or first capture."""
        self.update(0.0)
        print("[excavator-motion] Applied trajectory targets at t=0")

    def trajectory_info(self) -> dict[str, Any]:
        return {
            "path": str(self.trajectory.source_path),
            "sha256": self.trajectory.sha256,
            "keyframe_count": len(self.trajectory.keyframes),
            "duration_seconds": self.trajectory.duration,
            "playback_mode": self.playback_mode,
            "interpolation": self.interpolation,
        }

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "joint_path": joint.spec.path,
                "body_path": joint.spec.body_path,
                "lower_limit_degrees": joint.lower_limit,
                "upper_limit_degrees": joint.upper_limit,
                "trajectory_min_degrees": min(
                    frame.targets[name] for frame in self.trajectory.keyframes
                ),
                "trajectory_max_degrees": max(
                    frame.targets[name] for frame in self.trajectory.keyframes
                ),
            }
            for name, joint in self._joints.items()
        ]

    def _body_transforms(self) -> dict[str, list[float] | None]:
        from pxr import Usd, UsdGeom

        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        transforms: dict[str, list[float] | None] = {}
        for name, joint in self._joints.items():
            prim = self._stage.GetPrimAtPath(joint.spec.body_path)
            if not prim.IsValid():
                transforms[name] = None
                continue
            matrix = cache.GetLocalToWorldTransform(prim)
            transforms[name] = [
                float(matrix[row][column]) for row in range(4) for column in range(4)
            ]
        return transforms

    def get_state(self, simulation_time: float) -> dict[str, Any]:
        return {
            "enabled": True,
            "simulation_time": simulation_time,
            "trajectory_time": self._last_trajectory_time,
            "trajectory_path": str(self.trajectory.source_path),
            "target_degrees": {name: joint.target for name, joint in self._joints.items()},
            "body_world_transform": self._body_transforms(),
        }
