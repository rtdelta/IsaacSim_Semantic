"""Deterministic four-DOF Articulation trajectory playback.

The CSV format remains ``time,cab,boom,small_arm,bucket`` in degrees, but
playback no longer authors Angular Drive targets.  All four positions are
submitted to one fixed-base Articulation before a physics step and are read
back after that step so captured images and joint metadata describe the same
accepted runtime state.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from articulation_adapter import IsaacArticulationAdapter


JOINT_NAMES = ("cab", "boom", "small_arm", "bucket")
CONTROL_MODE = "articulation_direct_position"


@dataclass(frozen=True)
class TrajectoryKeyframe:
    time: float
    targets: dict[str, float]


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
                    raise ValueError(
                        f"Invalid numeric value in trajectory line {line_number}"
                    ) from exc
                if not math.isfinite(time_value) or any(
                    not math.isfinite(value) for value in targets.values()
                ):
                    raise ValueError(f"Non-finite value in trajectory line {line_number}")
                keyframes.append(TrajectoryKeyframe(time=time_value, targets=targets))

        if len(keyframes) < 2:
            raise ValueError("Trajectory must contain at least two keyframes")
        if not math.isclose(keyframes[0].time, 0.0, abs_tol=1e-12):
            raise ValueError("The first trajectory keyframe must start at time 0.0")
        if any(
            current.time <= previous.time
            for previous, current in zip(keyframes, keyframes[1:])
        ):
            raise ValueError("Trajectory times must be strictly increasing")
        return cls(path, keyframes)

    def sample(
        self,
        simulation_time: float,
        playback_mode: str = "loop",
    ) -> tuple[float, dict[str, float]]:
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
    """Play one degree-valued CSV through a fixed-base four-DOF Articulation."""

    def __init__(
        self,
        stage: Any,
        trajectory_path: str | Path,
        joint_profile: Any,
        stage_report: Any,
        playback_mode: str = "hold",
        interpolation: str = "linear",
        trajectory_metadata: Mapping[str, Any] | None = None,
        adapter: Any | None = None,
    ) -> None:
        self._stage = stage
        self.trajectory = JointTrajectory.from_csv(trajectory_path)
        self.joint_profile = joint_profile
        self.stage_report = stage_report
        self.playback_mode = playback_mode
        self.interpolation = interpolation
        self.trajectory_metadata = dict(trajectory_metadata or {}) or None
        self._adapter = adapter
        self._bound = False
        self._runtime_initialized = False
        self._last_dataset_time = 0.0
        self._last_trajectory_time = 0.0
        self._commanded = dict(self.trajectory.keyframes[0].targets)
        self._actual: dict[str, float] = {}
        self._position_error: dict[str, float] = {}

    @property
    def ready(self) -> bool:
        return bool(self._bound and self._adapter is not None and self._adapter.ready)

    def bind(self) -> None:
        """Validate trajectory/profile contracts and bind before Timeline playback."""
        if self._bound:
            raise RuntimeError("ExcavatorJointMotion is already bound")
        if self.playback_mode not in {"loop", "hold"}:
            raise ValueError("playback_mode must be 'loop' or 'hold'")
        if self.interpolation != "linear":
            raise ValueError("Trajectory playback supports interpolation='linear' only")
        profile_names = tuple(self.joint_profile.logical_joint_names)
        if profile_names != JOINT_NAMES:
            raise ValueError(
                f"Joint profile order must be {JOINT_NAMES}, got {profile_names}"
            )

        limits = self.stage_report.limits_degrees
        if set(limits) != set(JOINT_NAMES):
            raise RuntimeError("Articulation report does not contain all four safe joint limits")
        for frame_index, keyframe in enumerate(self.trajectory.keyframes):
            for name, position in keyframe.targets.items():
                safe_lower, safe_upper = limits[name]
                if not safe_lower <= position <= safe_upper:
                    raise ValueError(
                        f"Trajectory frame {frame_index} at t={keyframe.time}: {name}={position} "
                        f"is outside safe limits [{safe_lower}, {safe_upper}]"
                    )

        if self.playback_mode == "loop":
            first = self.trajectory.keyframes[0].targets
            last = self.trajectory.keyframes[-1].targets
            if any(
                not math.isclose(first[name], last[name], abs_tol=1e-9)
                for name in JOINT_NAMES
            ):
                raise ValueError(
                    "Loop trajectory must end at its initial joint positions; "
                    "recorded non-closed trajectories should use --trajectory-mode hold"
                )

        ordered_dof_names = tuple(
            self.stage_report.dof_names[name] for name in JOINT_NAMES
        )
        if self._adapter is None:
            self._adapter = IsaacArticulationAdapter(
                self.stage_report.articulation_root_path,
                ordered_dof_names,
            )
        self._adapter.bind()
        self._bound = True
        print(
            f"[excavator-motion] Bound {CONTROL_MODE}: root="
            f"{self.stage_report.articulation_root_path}, dofs={ordered_dof_names}"
        )

    def initialize_runtime(self) -> None:
        """Validate the tensor-backed Articulation after Timeline bootstrap."""
        if not self._bound or self._adapter is None:
            raise RuntimeError("ExcavatorJointMotion.bind() must run before runtime initialization")
        self._adapter.validate_runtime()
        self._set_actual(self._adapter.get_positions_degrees())
        self._runtime_initialized = True
        self._update_error()
        print(
            f"[excavator-motion] Runtime initialized: actual_degrees={self._actual}"
        )

    def apply_initial_positions(self) -> None:
        """Submit trajectory t=0 before a counted setup physics step."""
        self.before_physics_step(0.0)

    def before_physics_step(self, dataset_time: float) -> None:
        if not self._runtime_initialized or self._adapter is None:
            raise RuntimeError("Articulation runtime is not initialized")
        trajectory_time, positions = self.trajectory.sample(dataset_time, self.playback_mode)
        self._adapter.set_positions_degrees(tuple(positions[name] for name in JOINT_NAMES))
        self._last_dataset_time = float(dataset_time)
        self._last_trajectory_time = float(trajectory_time)
        self._commanded = dict(positions)

    def after_physics_step(self, dataset_time: float) -> None:
        if not self._runtime_initialized or self._adapter is None:
            raise RuntimeError("Articulation runtime is not initialized")
        self._set_actual(self._adapter.get_positions_degrees())
        self._last_dataset_time = float(dataset_time)
        self._update_error()
        tolerance = float(self.joint_profile.readback_tolerance_degrees)
        violations = {
            name: error
            for name, error in self._position_error.items()
            if abs(error) > tolerance
        }
        if violations:
            raise RuntimeError(
                "Articulation position readback exceeded "
                f"{tolerance} degree tolerance: {violations}"
            )

    def update(self, simulation_time: float) -> None:
        """Compatibility alias for the pre-physics command phase."""
        self.before_physics_step(simulation_time)

    def _set_actual(self, positions: Any) -> None:
        values = tuple(float(value) for value in positions)
        if len(values) != len(JOINT_NAMES):
            raise RuntimeError(
                f"Expected {len(JOINT_NAMES)} Articulation positions, got {len(values)}"
            )
        if any(not math.isfinite(value) for value in values):
            raise RuntimeError("Articulation returned a non-finite joint position")
        self._actual = dict(zip(JOINT_NAMES, values))

    def _update_error(self) -> None:
        self._position_error = {
            name: self._actual[name] - self._commanded[name]
            for name in JOINT_NAMES
            if name in self._actual
        }

    def trajectory_info(self) -> dict[str, Any]:
        return {
            "path": str(self.trajectory.source_path),
            "sha256": self.trajectory.sha256,
            "keyframe_count": len(self.trajectory.keyframes),
            "duration_seconds": self.trajectory.duration,
            "playback_mode": self.playback_mode,
            "interpolation": self.interpolation,
            "metadata": self.trajectory_metadata,
        }

    def binding_info(self) -> dict[str, Any]:
        adapter_info = (
            self._adapter.binding_info()
            if self._adapter is not None and hasattr(self._adapter, "binding_info")
            else {}
        )
        return {
            "control_mode": CONTROL_MODE,
            "articulation_root_path": self.stage_report.articulation_root_path,
            "joint_paths": dict(self.stage_report.joint_paths),
            "dof_names": dict(self.stage_report.dof_names),
            "body_paths": list(self.stage_report.body_paths),
            "safe_limits_degrees": {
                name: list(values)
                for name, values in self.stage_report.limits_degrees.items()
            },
            "adapter": adapter_info,
        }

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "joint_path": self.stage_report.joint_paths[name],
                "dof_name": self.stage_report.dof_names[name],
                "lower_limit_degrees": self.stage_report.limits_degrees[name][0],
                "upper_limit_degrees": self.stage_report.limits_degrees[name][1],
                "trajectory_min_degrees": min(
                    frame.targets[name] for frame in self.trajectory.keyframes
                ),
                "trajectory_max_degrees": max(
                    frame.targets[name] for frame in self.trajectory.keyframes
                ),
            }
            for name in JOINT_NAMES
        ]

    def _body_transforms(self) -> dict[str, list[float] | None]:
        from pxr import Usd, UsdGeom

        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        transforms: dict[str, list[float] | None] = {}
        body_paths = tuple(self.stage_report.body_paths)
        controlled_body_paths = body_paths[1:] if len(body_paths) == 5 else body_paths
        for name, body_path in zip(JOINT_NAMES, controlled_body_paths):
            prim = self._stage.GetPrimAtPath(body_path)
            if not prim.IsValid():
                transforms[name] = None
                continue
            matrix = cache.GetLocalToWorldTransform(prim)
            transforms[name] = [
                float(matrix[row][column]) for row in range(4) for column in range(4)
            ]
        return transforms

    def get_state(self, simulation_time: float | None = None) -> dict[str, Any]:
        if not self._runtime_initialized:
            raise RuntimeError("Articulation runtime is not initialized")
        return {
            "enabled": True,
            "control_mode": CONTROL_MODE,
            "simulation_time": (
                float(simulation_time)
                if simulation_time is not None
                else self._last_dataset_time
            ),
            "trajectory_time": self._last_trajectory_time,
            "trajectory_path": str(self.trajectory.source_path),
            "commanded_degrees": dict(self._commanded),
            "actual_degrees": dict(self._actual),
            "position_error_degrees": dict(self._position_error),
            # Keep the old key during the schema transition for downstream
            # consumers that only know how to display a requested angle.
            "target_degrees": dict(self._commanded),
            "body_world_transform": self._body_transforms(),
        }

    def shutdown(self) -> None:
        if self._adapter is not None:
            self._adapter.shutdown()
        self._bound = False
        self._runtime_initialized = False
