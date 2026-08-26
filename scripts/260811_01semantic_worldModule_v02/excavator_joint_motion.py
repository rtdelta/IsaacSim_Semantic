"""Deterministic excavator joint and optional floating-root trajectory playback.

Legacy CSV files contain ``time,cab,boom,small_arm,bucket`` in degrees.  Root
pose CSV files append an Isaac-style world quaternion (wxyz), diagnostic Euler
angles, and the Articulation-root world position in meters.  Joint and root
commands are submitted before physics; accepted state is read back afterwards
so captured images and motion metadata describe one auditable runtime state.
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
ROOT_CONTROL_MODE = "articulation_direct_world_pose"
ROOT_QUATERNION_COLUMNS = (
    "root_quat_w",
    "root_quat_x",
    "root_quat_y",
    "root_quat_z",
)
ROOT_EULER_COLUMNS = (
    "root_roll_x_deg",
    "root_pitch_y_deg",
    "root_yaw_z_deg",
)
ROOT_WORLD_POSITION_COLUMNS = (
    "root_world_x_m",
    "root_world_y_m",
    "root_world_z_m",
)
LEGACY_TRAJECTORY_COLUMNS = ("time", *JOINT_NAMES)
ROOT_POSE_TRAJECTORY_COLUMNS = (
    *LEGACY_TRAJECTORY_COLUMNS,
    *ROOT_QUATERNION_COLUMNS,
    *ROOT_EULER_COLUMNS,
    *ROOT_WORLD_POSITION_COLUMNS,
)


def _finite_tuple(values: Any, length: int, label: str) -> tuple[float, ...]:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain {length} numeric values") from exc
    if len(result) != length or any(not math.isfinite(value) for value in result):
        raise ValueError(f"{label} must contain {length} finite values")
    return result


def normalize_quaternion_wxyz(values: Any) -> tuple[float, float, float, float]:
    quaternion = _finite_tuple(values, 4, "Quaternion")
    norm = math.sqrt(sum(value * value for value in quaternion))
    if norm <= 1.0e-12:
        raise ValueError("Quaternion cannot be zero")
    return tuple(value / norm for value in quaternion)  # type: ignore[return-value]


def quaternion_conjugate_wxyz(values: Any) -> tuple[float, float, float, float]:
    w, x, y, z = normalize_quaternion_wxyz(values)
    return (w, -x, -y, -z)


def quaternion_multiply_wxyz(left: Any, right: Any) -> tuple[float, float, float, float]:
    lw, lx, ly, lz = normalize_quaternion_wxyz(left)
    rw, rx, ry, rz = normalize_quaternion_wxyz(right)
    return normalize_quaternion_wxyz(
        (
            lw * rw - lx * rx - ly * ry - lz * rz,
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
        )
    )


def rotate_vector_wxyz(orientation: Any, vector: Any) -> tuple[float, float, float]:
    w, x, y, z = normalize_quaternion_wxyz(orientation)
    vx, vy, vz = _finite_tuple(vector, 3, "Vector")
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def slerp_quaternion_wxyz(left: Any, right: Any, alpha: float) -> tuple[float, float, float, float]:
    """Interpolate two unit quaternions over the shortest rotation path."""

    amount = float(alpha)
    if not math.isfinite(amount) or not 0.0 <= amount <= 1.0:
        raise ValueError("Quaternion interpolation alpha must be inside [0, 1]")
    first = normalize_quaternion_wxyz(left)
    second = normalize_quaternion_wxyz(right)
    dot = sum(a * b for a, b in zip(first, second))
    if dot < 0.0:
        second = tuple(-value for value in second)  # type: ignore[assignment]
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        return normalize_quaternion_wxyz(
            tuple(a + amount * (b - a) for a, b in zip(first, second))
        )
    angle = math.acos(dot)
    denominator = math.sin(angle)
    left_weight = math.sin((1.0 - amount) * angle) / denominator
    right_weight = math.sin(amount * angle) / denominator
    return normalize_quaternion_wxyz(
        tuple(
            left_weight * a + right_weight * b
            for a, b in zip(first, second)
        )
    )


def quaternion_angular_error_degrees(left: Any, right: Any) -> float:
    first = normalize_quaternion_wxyz(left)
    second = normalize_quaternion_wxyz(right)
    dot = max(0.0, min(1.0, abs(sum(a * b for a, b in zip(first, second)))))
    return math.degrees(2.0 * math.acos(dot))


@dataclass(frozen=True)
class TrajectoryKeyframe:
    time: float
    targets: dict[str, float]
    root_position_meters: tuple[float, float, float] | None = None
    root_orientation_wxyz: tuple[float, float, float, float] | None = None
    recorded_euler_xyz_degrees: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class TrajectorySample:
    trajectory_time: float
    targets: dict[str, float]
    root_position_meters: tuple[float, float, float] | None
    root_orientation_wxyz: tuple[float, float, float, float] | None


class JointTrajectory:
    """Validated in-memory keyframes loaded from one CSV file."""

    def __init__(self, source_path: Path, keyframes: list[TrajectoryKeyframe]) -> None:
        self.source_path = Path(source_path).resolve()
        self.keyframes = keyframes
        self.times = [frame.time for frame in keyframes]
        self.duration = self.times[-1]
        self.sha256 = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        root_flags = [frame.root_position_meters is not None for frame in keyframes]
        if any(root_flags) and not all(root_flags):
            raise ValueError("Root pose must be present on every trajectory keyframe")
        self.has_root_pose = bool(root_flags and root_flags[0])
        self.columns = (
            ROOT_POSE_TRAJECTORY_COLUMNS
            if self.has_root_pose
            else LEGACY_TRAJECTORY_COLUMNS
        )

    @classmethod
    def from_csv(cls, source_path: str | Path) -> "JointTrajectory":
        path = Path(source_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Trajectory CSV not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = tuple(reader.fieldnames or ())
            if fieldnames not in {
                LEGACY_TRAJECTORY_COLUMNS,
                ROOT_POSE_TRAJECTORY_COLUMNS,
            }:
                raise ValueError(
                    "Trajectory columns must exactly match either "
                    f"{LEGACY_TRAJECTORY_COLUMNS} or {ROOT_POSE_TRAJECTORY_COLUMNS}, "
                    f"got {reader.fieldnames}"
                )
            has_root_pose = fieldnames == ROOT_POSE_TRAJECTORY_COLUMNS
            keyframes: list[TrajectoryKeyframe] = []
            for line_number, row in enumerate(reader, start=2):
                try:
                    time_value = float(row["time"])
                    targets = {name: float(row[name]) for name in JOINT_NAMES}
                    root_orientation = (
                        normalize_quaternion_wxyz(
                            tuple(row[name] for name in ROOT_QUATERNION_COLUMNS)
                        )
                        if has_root_pose
                        else None
                    )
                    recorded_euler = (
                        _finite_tuple(
                            tuple(row[name] for name in ROOT_EULER_COLUMNS),
                            3,
                            f"Trajectory Euler values at line {line_number}",
                        )
                        if has_root_pose
                        else None
                    )
                    root_position = (
                        _finite_tuple(
                            tuple(row[name] for name in ROOT_WORLD_POSITION_COLUMNS),
                            3,
                            f"Trajectory root position at line {line_number}",
                        )
                        if has_root_pose
                        else None
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid numeric value in trajectory line {line_number}"
                    ) from exc
                if not math.isfinite(time_value) or any(
                    not math.isfinite(value) for value in targets.values()
                ):
                    raise ValueError(f"Non-finite value in trajectory line {line_number}")
                keyframes.append(
                    TrajectoryKeyframe(
                        time=time_value,
                        targets=targets,
                        root_position_meters=root_position,  # type: ignore[arg-type]
                        root_orientation_wxyz=root_orientation,
                        recorded_euler_xyz_degrees=recorded_euler,  # type: ignore[arg-type]
                    )
                )

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
        """Backward-compatible joint-only view of :meth:`sample_state`."""

        sample = self.sample_state(simulation_time, playback_mode)
        return sample.trajectory_time, sample.targets

    def sample_state(
        self,
        simulation_time: float,
        playback_mode: str = "loop",
    ) -> TrajectorySample:
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
            return self._sample_from_frame(trajectory_time, self.keyframes[0])
        if trajectory_time >= self.times[-1]:
            return self._sample_from_frame(trajectory_time, self.keyframes[-1])

        right = bisect.bisect_right(self.times, trajectory_time)
        left_frame = self.keyframes[right - 1]
        right_frame = self.keyframes[right]
        alpha = (trajectory_time - left_frame.time) / (right_frame.time - left_frame.time)
        targets = {
            name: left_frame.targets[name]
            + alpha * (right_frame.targets[name] - left_frame.targets[name])
            for name in JOINT_NAMES
        }
        if self.has_root_pose:
            assert left_frame.root_position_meters is not None
            assert right_frame.root_position_meters is not None
            assert left_frame.root_orientation_wxyz is not None
            assert right_frame.root_orientation_wxyz is not None
            root_position = tuple(
                left + alpha * (right_value - left)
                for left, right_value in zip(
                    left_frame.root_position_meters,
                    right_frame.root_position_meters,
                )
            )
            root_orientation = slerp_quaternion_wxyz(
                left_frame.root_orientation_wxyz,
                right_frame.root_orientation_wxyz,
                alpha,
            )
        else:
            root_position = None
            root_orientation = None
        return TrajectorySample(
            trajectory_time=trajectory_time,
            targets=targets,
            root_position_meters=root_position,  # type: ignore[arg-type]
            root_orientation_wxyz=root_orientation,
        )

    @staticmethod
    def _sample_from_frame(
        trajectory_time: float,
        frame: TrajectoryKeyframe,
    ) -> TrajectorySample:
        return TrajectorySample(
            trajectory_time=float(trajectory_time),
            targets=dict(frame.targets),
            root_position_meters=frame.root_position_meters,
            root_orientation_wxyz=frame.root_orientation_wxyz,
        )


class ExcavatorJointMotion:
    """Play joint-only or joint-plus-root CSV state through one Articulation."""

    def __init__(
        self,
        stage: Any,
        trajectory_path: str | Path,
        joint_profile: Any,
        stage_report: Any,
        playback_mode: str = "hold",
        interpolation: str = "linear",
        trajectory_metadata: Mapping[str, Any] | None = None,
        root_pose_playback: Any | None = None,
        adapter: Any | None = None,
    ) -> None:
        self._stage = stage
        self.trajectory = JointTrajectory.from_csv(trajectory_path)
        self.joint_profile = joint_profile
        self.stage_report = stage_report
        self.playback_mode = playback_mode
        self.interpolation = interpolation
        self.trajectory_metadata = dict(trajectory_metadata or {}) or None
        self.root_pose_playback = root_pose_playback
        self._root_enabled = bool(
            root_pose_playback is not None
            and getattr(root_pose_playback, "enabled", False)
        )
        self._root_coordinate_mode = str(
            getattr(root_pose_playback, "coordinate_mode", "absolute_world")
        )
        self._root_apply_policy = str(
            getattr(root_pose_playback, "apply_policy", "authoritative_pose")
        )
        self._root_position_tolerance = float(
            getattr(root_pose_playback, "position_tolerance_meters", 0.001)
        )
        self._root_orientation_tolerance = float(
            getattr(root_pose_playback, "orientation_tolerance_degrees", 0.05)
        )
        self._adapter = adapter
        self._bound = False
        self._runtime_initialized = False
        self._last_dataset_time = 0.0
        self._last_trajectory_time = 0.0
        self._commanded = dict(self.trajectory.keyframes[0].targets)
        self._actual: dict[str, float] = {}
        self._position_error: dict[str, float] = {}
        first_frame = self.trajectory.keyframes[0]
        self._commanded_root_position = first_frame.root_position_meters
        self._commanded_root_orientation = first_frame.root_orientation_wxyz
        self._physics_root_position: tuple[float, float, float] | None = None
        self._physics_root_orientation: tuple[float, float, float, float] | None = None
        self._capture_root_position: tuple[float, float, float] | None = None
        self._capture_root_orientation: tuple[float, float, float, float] | None = None
        self._root_position_error: tuple[float, float, float] | None = None
        self._root_position_error_norm: float | None = None
        self._root_orientation_error_degrees: float | None = None
        self._root_pose_reasserted = False
        self._source_initial_root_position = first_frame.root_position_meters
        self._source_initial_root_orientation = first_frame.root_orientation_wxyz
        self._target_initial_root_position: tuple[float, float, float] | None = None
        self._target_initial_root_orientation: tuple[float, float, float, float] | None = None

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
        if self.trajectory.has_root_pose != self._root_enabled:
            if self.trajectory.has_root_pose:
                raise ValueError(
                    "Root-pose trajectory requires root_pose_playback.enabled=true"
                )
            raise ValueError(
                "root_pose_playback.enabled=true requires a root-pose trajectory CSV"
            )
        if self._root_enabled:
            if self._root_coordinate_mode not in {"absolute_world", "relative_to_initial"}:
                raise ValueError(
                    "root pose coordinate_mode must be 'absolute_world' or "
                    "'relative_to_initial'"
                )
            if self._root_apply_policy not in {"authoritative_pose", "physics_accepted"}:
                raise ValueError(
                    "root pose apply_policy must be 'authoritative_pose' or "
                    "'physics_accepted'"
                )
            if self._root_position_tolerance <= 0 or not math.isfinite(
                self._root_position_tolerance
            ):
                raise ValueError("Root position tolerance must be positive and finite")
            if self._root_orientation_tolerance <= 0 or not math.isfinite(
                self._root_orientation_tolerance
            ):
                raise ValueError("Root orientation tolerance must be positive and finite")
            if bool(getattr(self.joint_profile, "require_fixed_base", True)):
                raise ValueError("Root-pose playback requires a floating-base joint profile")
            if not bool(
                getattr(self.joint_profile, "require_floating_base", False)
            ):
                raise ValueError(
                    "Root-pose playback requires profile require_floating_base=true"
                )
            if not bool(
                getattr(self.joint_profile, "root_pose_playback_supported", False)
            ):
                raise ValueError(
                    "Root-pose playback requires profile "
                    "root_pose_playback_supported=true"
                )
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
            first_frame = self.trajectory.keyframes[0]
            last_frame = self.trajectory.keyframes[-1]
            first = first_frame.targets
            last = last_frame.targets
            if any(
                not math.isclose(first[name], last[name], abs_tol=1e-9)
                for name in JOINT_NAMES
            ):
                raise ValueError(
                    "Loop trajectory must end at its initial joint positions; "
                    "recorded non-closed trajectories should use --trajectory-mode hold"
                )
            if self._root_enabled:
                assert first_frame.root_position_meters is not None
                assert last_frame.root_position_meters is not None
                assert first_frame.root_orientation_wxyz is not None
                assert last_frame.root_orientation_wxyz is not None
                position_delta = math.sqrt(
                    sum(
                        (end - start) ** 2
                        for start, end in zip(
                            first_frame.root_position_meters,
                            last_frame.root_position_meters,
                        )
                    )
                )
                orientation_delta = quaternion_angular_error_degrees(
                    first_frame.root_orientation_wxyz,
                    last_frame.root_orientation_wxyz,
                )
                if position_delta > self._root_position_tolerance or (
                    orientation_delta > self._root_orientation_tolerance
                ):
                    raise ValueError(
                        "Loop trajectory must close its root pose; "
                        f"position_delta={position_delta}, "
                        f"orientation_delta_degrees={orientation_delta}"
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
        if self._root_enabled:
            for method_name in ("get_root_world_pose", "set_root_world_pose"):
                if not callable(getattr(self._adapter, method_name, None)):
                    raise RuntimeError(
                        f"Root-pose playback adapter lacks {method_name}()"
                    )
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
        if self._root_enabled:
            position, orientation = self._adapter.get_root_world_pose()
            self._target_initial_root_position = _finite_tuple(
                position, 3, "Initial target root position"
            )  # type: ignore[assignment]
            self._target_initial_root_orientation = normalize_quaternion_wxyz(
                orientation
            )
            self._physics_root_position = self._target_initial_root_position
            self._physics_root_orientation = self._target_initial_root_orientation
            self._capture_root_position = self._target_initial_root_position
            self._capture_root_orientation = self._target_initial_root_orientation
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
        sample = self.trajectory.sample_state(dataset_time, self.playback_mode)
        self._adapter.set_positions_degrees(
            tuple(sample.targets[name] for name in JOINT_NAMES)
        )
        if self._root_enabled:
            root_position, root_orientation = self._mapped_root_pose(sample)
            self._adapter.set_root_world_pose(root_position, root_orientation)
            self._commanded_root_position = root_position
            self._commanded_root_orientation = root_orientation
        self._last_dataset_time = float(dataset_time)
        self._last_trajectory_time = float(sample.trajectory_time)
        self._commanded = dict(sample.targets)
        self._root_pose_reasserted = False

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
        if self._root_enabled:
            physics_position, physics_orientation = self._adapter.get_root_world_pose()
            self._physics_root_position = _finite_tuple(
                physics_position, 3, "Physics root position"
            )  # type: ignore[assignment]
            self._physics_root_orientation = normalize_quaternion_wxyz(
                physics_orientation
            )
            position_error, position_norm, orientation_error = self._root_errors(
                self._physics_root_position,
                self._physics_root_orientation,
            )
            if self._root_apply_policy == "authoritative_pose" and (
                position_norm > self._root_position_tolerance
                or orientation_error > self._root_orientation_tolerance
            ):
                assert self._commanded_root_position is not None
                assert self._commanded_root_orientation is not None
                self._adapter.set_root_world_pose(
                    self._commanded_root_position,
                    self._commanded_root_orientation,
                )
                self._root_pose_reasserted = True
                capture_position, capture_orientation = self._adapter.get_root_world_pose()
                self._capture_root_position = _finite_tuple(
                    capture_position, 3, "Capture root position"
                )  # type: ignore[assignment]
                self._capture_root_orientation = normalize_quaternion_wxyz(
                    capture_orientation
                )
            else:
                self._capture_root_position = self._physics_root_position
                self._capture_root_orientation = self._physics_root_orientation
            (
                self._root_position_error,
                self._root_position_error_norm,
                self._root_orientation_error_degrees,
            ) = self._root_errors(
                self._capture_root_position,
                self._capture_root_orientation,
            )
            if (
                self._root_position_error_norm > self._root_position_tolerance
                or self._root_orientation_error_degrees
                > self._root_orientation_tolerance
            ):
                raise RuntimeError(
                    "Articulation root-pose readback exceeded tolerance: "
                    f"position_error_meters={self._root_position_error_norm}, "
                    "orientation_error_degrees="
                    f"{self._root_orientation_error_degrees}"
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

    def _mapped_root_pose(
        self,
        sample: TrajectorySample,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        if sample.root_position_meters is None or sample.root_orientation_wxyz is None:
            raise RuntimeError("Root-pose playback sample does not contain a complete root pose")
        if self._root_coordinate_mode == "absolute_world":
            return sample.root_position_meters, sample.root_orientation_wxyz
        if (
            self._source_initial_root_position is None
            or self._source_initial_root_orientation is None
            or self._target_initial_root_position is None
            or self._target_initial_root_orientation is None
        ):
            raise RuntimeError("Relative root-pose calibration is not initialized")
        source_delta_world = tuple(
            current - initial
            for current, initial in zip(
                sample.root_position_meters,
                self._source_initial_root_position,
            )
        )
        source_delta_local = rotate_vector_wxyz(
            quaternion_conjugate_wxyz(self._source_initial_root_orientation),
            source_delta_world,
        )
        target_delta_world = rotate_vector_wxyz(
            self._target_initial_root_orientation,
            source_delta_local,
        )
        target_position = tuple(
            initial + delta
            for initial, delta in zip(
                self._target_initial_root_position,
                target_delta_world,
            )
        )
        relative_orientation = quaternion_multiply_wxyz(
            quaternion_conjugate_wxyz(self._source_initial_root_orientation),
            sample.root_orientation_wxyz,
        )
        target_orientation = quaternion_multiply_wxyz(
            self._target_initial_root_orientation,
            relative_orientation,
        )
        return target_position, target_orientation  # type: ignore[return-value]

    def _root_errors(
        self,
        actual_position: tuple[float, float, float] | None,
        actual_orientation: tuple[float, float, float, float] | None,
    ) -> tuple[tuple[float, float, float], float, float]:
        if (
            self._commanded_root_position is None
            or self._commanded_root_orientation is None
            or actual_position is None
            or actual_orientation is None
        ):
            raise RuntimeError("Root-pose error requested without complete root state")
        position_error = tuple(
            actual - commanded
            for actual, commanded in zip(
                actual_position,
                self._commanded_root_position,
            )
        )
        position_norm = math.sqrt(sum(value * value for value in position_error))
        orientation_error = quaternion_angular_error_degrees(
            self._commanded_root_orientation,
            actual_orientation,
        )
        return position_error, position_norm, orientation_error  # type: ignore[return-value]

    def _trajectory_metadata_provenance(self) -> dict[str, Any]:
        describe = getattr(self.joint_profile, "trajectory_metadata_provenance", None)
        if callable(describe):
            return describe(
                self.trajectory.source_path,
                self.trajectory_metadata,
                root_pose_enabled=self._root_enabled,
                coordinate_mode=self._root_coordinate_mode,
            )
        contract = getattr(self.joint_profile, "trajectory_metadata", None)
        return {
            "present": self.trajectory_metadata is not None,
            "required": bool(
                getattr(contract, "require_root_motion_metadata", False)
            ),
            "expected_sidecar_path": str(
                self.trajectory.source_path.with_name(
                    f"{self.trajectory.source_path.stem}.metadata.json"
                )
            ),
            "source_contract_basis": (
                "recorder_sidecar"
                if self.trajectory_metadata is not None
                else (
                    "csv_absolute_world_user_assertion"
                    if self._root_enabled
                    and self._root_coordinate_mode == "absolute_world"
                    else "csv_schema"
                )
            ),
        }

    def trajectory_info(self) -> dict[str, Any]:
        first_frame = self.trajectory.keyframes[0]
        root_position_changes = False
        root_orientation_changes = False
        if self.trajectory.has_root_pose:
            assert first_frame.root_position_meters is not None
            assert first_frame.root_orientation_wxyz is not None
            root_position_changes = any(
                frame.root_position_meters is not None
                and any(
                    not math.isclose(actual, initial, abs_tol=1.0e-12)
                    for actual, initial in zip(
                        frame.root_position_meters,
                        first_frame.root_position_meters,
                    )
                )
                for frame in self.trajectory.keyframes[1:]
            )
            root_orientation_changes = any(
                frame.root_orientation_wxyz is not None
                and quaternion_angular_error_degrees(
                    first_frame.root_orientation_wxyz,
                    frame.root_orientation_wxyz,
                )
                > 1.0e-9
                for frame in self.trajectory.keyframes[1:]
            )
        return {
            "path": str(self.trajectory.source_path),
            "sha256": self.trajectory.sha256,
            "keyframe_count": len(self.trajectory.keyframes),
            "duration_seconds": self.trajectory.duration,
            "schema": (
                "joint_and_root_pose_v1"
                if self.trajectory.has_root_pose
                else "joint_only_v1"
            ),
            "columns": list(self.trajectory.columns),
            "root_pose_included": self.trajectory.has_root_pose,
            "root_position_changes": root_position_changes,
            "root_orientation_changes": root_orientation_changes,
            "playback_mode": self.playback_mode,
            "interpolation": self.interpolation,
            "root_position_interpolation": (
                "linear" if self._root_enabled else None
            ),
            "root_orientation_interpolation": (
                "slerp" if self._root_enabled else None
            ),
            "metadata": self.trajectory_metadata,
            "metadata_provenance": self._trajectory_metadata_provenance(),
        }

    def binding_info(self) -> dict[str, Any]:
        adapter_info = (
            self._adapter.binding_info()
            if self._adapter is not None and hasattr(self._adapter, "binding_info")
            else {}
        )
        return {
            "control_mode": CONTROL_MODE,
            "root_control_mode": ROOT_CONTROL_MODE if self._root_enabled else None,
            "root_pose_playback": {
                "enabled": self._root_enabled,
                "coordinate_mode": self._root_coordinate_mode,
                "apply_policy": self._root_apply_policy,
                "position_tolerance_meters": self._root_position_tolerance,
                "orientation_tolerance_degrees": self._root_orientation_tolerance,
                "coordinate_contract": (
                    {
                        "csv_position_unit": "meter",
                        "csv_quaternion_order": "wxyz",
                        "target_meters_per_unit": getattr(
                            self.stage_report, "meters_per_unit", None
                        ),
                        "target_up_axis": getattr(
                            self.stage_report, "up_axis", None
                        ),
                        "source_stage_path": (
                            self.trajectory_metadata.get("stage")
                            if self.trajectory_metadata is not None
                            else None
                        ),
                        "source_contract_basis": (
                            "recorder_sidecar"
                            if self.trajectory_metadata is not None
                            else "csv_absolute_world_user_assertion"
                        ),
                        "source_initial_position_meters": self._source_initial_root_position,
                        "source_initial_orientation_wxyz": self._source_initial_root_orientation,
                        "target_initial_position_meters": self._target_initial_root_position,
                        "target_initial_orientation_wxyz": self._target_initial_root_orientation,
                    }
                    if self._root_enabled
                    else None
                ),
            },
            "articulation_root_path": self.stage_report.articulation_root_path,
            "root_body_path": getattr(self.stage_report, "root_body_path", None),
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
        body_names = ("root", *JOINT_NAMES) if len(body_paths) == 5 else JOINT_NAMES
        for name, body_path in zip(body_names, body_paths):
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
            "root_control_mode": ROOT_CONTROL_MODE if self._root_enabled else None,
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
            "root_pose": {
                "enabled": self._root_enabled,
                "coordinate_mode": self._root_coordinate_mode if self._root_enabled else None,
                "apply_policy": self._root_apply_policy if self._root_enabled else None,
                "commanded_position_meters": self._commanded_root_position,
                "commanded_orientation_wxyz": self._commanded_root_orientation,
                "physics_readback_position_meters": self._physics_root_position,
                "physics_readback_orientation_wxyz": self._physics_root_orientation,
                "capture_position_meters": self._capture_root_position,
                "capture_orientation_wxyz": self._capture_root_orientation,
                "position_error_meters": self._root_position_error,
                "position_error_norm_meters": self._root_position_error_norm,
                "orientation_error_degrees": self._root_orientation_error_degrees,
                "reasserted_after_physics": self._root_pose_reasserted,
            },
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
