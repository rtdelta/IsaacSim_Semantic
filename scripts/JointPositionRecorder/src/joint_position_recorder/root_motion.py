"""Pure local-axis root-pose integration for direct WASD+FG excavator motion."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


class RootMotionError(ValueError):
    """Raised when a root pose or direct-motion request is invalid."""


@dataclass(frozen=True)
class RootPose:
    """One world-space root pose using an Isaac-style wxyz quaternion."""

    position_meters: tuple[float, float, float]
    orientation_wxyz: tuple[float, float, float, float]


def integrate_planar_root_pose(
    position_meters: Sequence[float],
    orientation_wxyz: Sequence[float],
    forward_axis: float,
    turn_axis: float,
    linear_speed_meters_per_second: float,
    angular_speed_degrees_per_second: float,
    dt: float,
    vertical_axis: float = 0.0,
    vertical_speed_meters_per_second: float | None = None,
) -> RootPose:
    """Advance a root along local X/Z and rotate around local Z for one frame.

    ``forward_axis``, ``turn_axis`` and ``vertical_axis`` are normalized command
    values in ``[-1, 1]``. Positive turn rotates toward local Z+, which is the
    excavator's left-turn convention. Positive vertical motion follows the
    current root Local Z+ direction. Horizontal translation uses the midpoint
    orientation so a simultaneous forward-and-turn command follows a smooth arc.
    """

    position = _finite_tuple(position_meters, 3, "position_meters")
    orientation = normalize_quaternion_wxyz(orientation_wxyz)
    forward = _bounded_axis(forward_axis, "forward_axis")
    turn = _bounded_axis(turn_axis, "turn_axis")
    vertical = _bounded_axis(vertical_axis, "vertical_axis")
    linear_speed = _positive_finite(
        linear_speed_meters_per_second, "linear_speed_meters_per_second"
    )
    angular_speed = _positive_finite(
        angular_speed_degrees_per_second, "angular_speed_degrees_per_second"
    )
    vertical_speed = _positive_finite(
        linear_speed
        if vertical_speed_meters_per_second is None
        else vertical_speed_meters_per_second,
        "vertical_speed_meters_per_second",
    )
    dt_value = _positive_finite(dt, "dt")

    yaw_step = math.radians(angular_speed) * turn * dt_value
    half_step_orientation = quaternion_multiply_wxyz(
        orientation, yaw_quaternion_wxyz(yaw_step * 0.5)
    )
    next_orientation = normalize_quaternion_wxyz(
        quaternion_multiply_wxyz(orientation, yaw_quaternion_wxyz(yaw_step))
    )
    forward_world = rotate_vector_wxyz(half_step_orientation, (1.0, 0.0, 0.0))
    vertical_world = rotate_vector_wxyz(orientation, (0.0, 0.0, 1.0))
    distance = linear_speed * forward * dt_value
    vertical_distance = vertical_speed * vertical * dt_value
    next_position = tuple(
        position[index]
        + forward_world[index] * distance
        + vertical_world[index] * vertical_distance
        for index in range(3)
    )
    return RootPose(next_position, next_orientation)


def yaw_quaternion_wxyz(angle_radians: float) -> tuple[float, float, float, float]:
    angle = float(angle_radians)
    if not math.isfinite(angle):
        raise RootMotionError("yaw angle must be finite")
    half = angle * 0.5
    return (math.cos(half), 0.0, 0.0, math.sin(half))


def quaternion_multiply_wxyz(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float]:
    lw, lx, ly, lz = _finite_tuple(left, 4, "left quaternion")
    rw, rx, ry, rz = _finite_tuple(right, 4, "right quaternion")
    return (
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    )


def normalize_quaternion_wxyz(
    value: Sequence[float],
) -> tuple[float, float, float, float]:
    quaternion = _finite_tuple(value, 4, "orientation_wxyz")
    norm = math.sqrt(sum(component * component for component in quaternion))
    if norm <= 1.0e-12:
        raise RootMotionError("orientation_wxyz cannot be a zero quaternion")
    return tuple(component / norm for component in quaternion)


def rotate_vector_wxyz(
    orientation_wxyz: Sequence[float], vector: Sequence[float]
) -> tuple[float, float, float]:
    """Rotate a 3D vector without constructing temporary quaternion objects."""

    w, x, y, z = normalize_quaternion_wxyz(orientation_wxyz)
    vx, vy, vz = _finite_tuple(vector, 3, "vector")
    # Equivalent to q * [0, v] * conjugate(q).
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def yaw_degrees_from_quaternion_wxyz(orientation_wxyz: Sequence[float]) -> float:
    """Return the world-Z yaw used for a compact GUI status readout."""

    w, x, y, z = normalize_quaternion_wxyz(orientation_wxyz)
    sin_yaw = 2.0 * (w * z + x * y)
    cos_yaw = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(sin_yaw, cos_yaw))


def euler_xyz_degrees_from_quaternion_wxyz(
    orientation_wxyz: Sequence[float],
) -> tuple[float, float, float]:
    """Return roll-X, pitch-Y, yaw-Z angles in degrees.

    The decomposition is the common Tait-Bryan convention
    ``Rz(yaw) * Ry(pitch) * Rx(roll)``. Roll and yaw are reported in
    ``[-180, 180]`` and pitch in ``[-90, 90]``. The quaternion remains the
    lossless representation in recorded CSV files; these Euler values are
    included for inspection and downstream tools that expect angles.
    """

    w, x, y, z = normalize_quaternion_wxyz(orientation_wxyz)
    sin_roll = 2.0 * (w * x + y * z)
    cos_roll = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sin_roll, cos_roll)

    sin_pitch = 2.0 * (w * y - z * x)
    pitch = math.asin(max(-1.0, min(1.0, sin_pitch)))

    sin_yaw = 2.0 * (w * z + x * y)
    cos_yaw = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(sin_yaw, cos_yaw)
    return tuple(math.degrees(value) for value in (roll, pitch, yaw))


def _finite_tuple(value: Sequence[float], size: int, name: str) -> tuple[float, ...]:
    result = tuple(float(component) for component in value)
    if len(result) != size or any(not math.isfinite(component) for component in result):
        raise RootMotionError(f"{name} must contain {size} finite values")
    return result


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise RootMotionError(f"{name} must be positive and finite")
    return result


def _bounded_axis(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or not -1.0 <= result <= 1.0:
        raise RootMotionError(f"{name} must be finite and inside [-1, 1]")
    return result
