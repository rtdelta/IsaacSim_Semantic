"""Pure-Python excavator trajectory loading, validation, and interpolation."""

from __future__ import annotations

import bisect
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


JOINT_NAMES = ("cab", "boom", "small_arm", "bucket")
CSV_COLUMNS = ("time", *JOINT_NAMES)


@dataclass(frozen=True)
class TrajectoryKeyframe:
    time: float
    targets: dict[str, float]


def normalized_targets(targets: Mapping[str, float]) -> dict[str, float]:
    """Return a finite, exactly-four-joint target dictionary."""

    if set(targets) != set(JOINT_NAMES):
        raise ValueError(f"Targets must contain exactly these joints: {JOINT_NAMES}")
    result = {name: float(targets[name]) for name in JOINT_NAMES}
    if any(not math.isfinite(value) for value in result.values()):
        raise ValueError("Joint targets must all be finite")
    return result


class JointTrajectory:
    """Validated keyframes compatible with the existing semantic-capture player."""

    def __init__(self, source_path: Path, keyframes: list[TrajectoryKeyframe]) -> None:
        self.source_path = Path(source_path).resolve()
        self.keyframes = keyframes
        self.times = [frame.time for frame in keyframes]
        self.duration = self.times[-1]

    @classmethod
    def from_csv(cls, source_path: str | Path) -> "JointTrajectory":
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Trajectory CSV not found: {path}")

        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(CSV_COLUMNS):
                raise ValueError(
                    f"Trajectory columns must be exactly {CSV_COLUMNS}, got {reader.fieldnames}"
                )

            keyframes: list[TrajectoryKeyframe] = []
            for line_number, row in enumerate(reader, start=2):
                try:
                    time_value = float(row["time"])
                    targets = normalized_targets({name: float(row[name]) for name in JOINT_NAMES})
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid numeric value in trajectory line {line_number}"
                    ) from exc
                if not math.isfinite(time_value):
                    raise ValueError(f"Non-finite time in trajectory line {line_number}")
                keyframes.append(TrajectoryKeyframe(time=time_value, targets=targets))

        if len(keyframes) < 2:
            raise ValueError("Trajectory must contain at least two samples")
        if not math.isclose(keyframes[0].time, 0.0, abs_tol=1e-12):
            raise ValueError("The first trajectory sample must start at time 0.0")
        if any(
            current.time <= previous.time
            for previous, current in zip(keyframes, keyframes[1:])
        ):
            raise ValueError("Trajectory times must be strictly increasing")
        return cls(path, keyframes)

    def sample(
        self, simulation_time: float, playback_mode: str = "hold"
    ) -> tuple[float, dict[str, float]]:
        if simulation_time < 0:
            raise ValueError("simulation_time must be non-negative")
        if playback_mode == "loop":
            trajectory_time = simulation_time % self.duration
            if simulation_time > 0 and math.isclose(
                trajectory_time, 0.0, abs_tol=1e-12
            ):
                trajectory_time = self.duration
        elif playback_mode == "hold":
            trajectory_time = min(simulation_time, self.duration)
        else:
            raise ValueError("playback_mode must be 'hold' or 'loop'")

        if trajectory_time <= self.times[0]:
            return trajectory_time, dict(self.keyframes[0].targets)
        if trajectory_time >= self.times[-1]:
            return trajectory_time, dict(self.keyframes[-1].targets)

        right = bisect.bisect_right(self.times, trajectory_time)
        left_frame = self.keyframes[right - 1]
        right_frame = self.keyframes[right]
        alpha = (trajectory_time - left_frame.time) / (
            right_frame.time - left_frame.time
        )
        targets = {
            name: left_frame.targets[name]
            + alpha * (right_frame.targets[name] - left_frame.targets[name])
            for name in JOINT_NAMES
        }
        return trajectory_time, targets

