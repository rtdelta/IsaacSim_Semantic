"""Deterministic constant-angular-speed position planning without dynamics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


class PlannerError(ValueError):
    """Raised when a motion request cannot produce a valid deterministic step."""


@dataclass(frozen=True)
class PlannerResult:
    """One synchronized multi-joint planner output."""

    positions_degrees: tuple[float, ...]
    reached: tuple[bool, ...]

    @property
    def all_reached(self) -> bool:
        return all(self.reached)


class ConstantSpeedPlanner:
    """Move independent joints toward targets at configured angular speeds."""

    def __init__(self, arrival_tolerance_degrees: float = 0.01) -> None:
        tolerance = float(arrival_tolerance_degrees)
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise PlannerError("arrival_tolerance_degrees must be positive and finite")
        self.arrival_tolerance_degrees = tolerance

    def step(
        self,
        current_degrees: Sequence[float],
        target_degrees: Sequence[float],
        speed_degrees_per_second: Sequence[float],
        dt: float,
    ) -> PlannerResult:
        """Return the next positions without overshooting any target."""

        current = tuple(float(value) for value in current_degrees)
        targets = tuple(float(value) for value in target_degrees)
        speeds = tuple(float(value) for value in speed_degrees_per_second)
        if not current or len(current) != len(targets) or len(current) != len(speeds):
            raise PlannerError("current, target, and speed arrays must have the same non-zero length")
        dt_value = float(dt)
        if not math.isfinite(dt_value) or dt_value <= 0:
            raise PlannerError("dt must be positive and finite")
        if any(not math.isfinite(value) for value in (*current, *targets, *speeds)):
            raise PlannerError("all joint values must be finite")
        if any(speed <= 0 for speed in speeds):
            raise PlannerError("all angular speeds must be positive")

        next_positions: list[float] = []
        reached: list[bool] = []
        for position, target, speed in zip(current, targets, speeds):
            error = target - position
            maximum_step = speed * dt_value
            if abs(error) <= self.arrival_tolerance_degrees or abs(error) <= maximum_step:
                next_positions.append(target)
                reached.append(True)
            else:
                next_positions.append(position + math.copysign(maximum_step, error))
                reached.append(False)
        return PlannerResult(tuple(next_positions), tuple(reached))

    @staticmethod
    def expected_duration_seconds(
        current_degrees: Sequence[float],
        target_degrees: Sequence[float],
        speed_degrees_per_second: Sequence[float],
    ) -> float:
        """Return the time until every independently moving joint has arrived."""

        current = tuple(float(value) for value in current_degrees)
        targets = tuple(float(value) for value in target_degrees)
        speeds = tuple(float(value) for value in speed_degrees_per_second)
        if not current or len(current) != len(targets) or len(current) != len(speeds):
            raise PlannerError("current, target, and speed arrays must have the same non-zero length")
        if any(not math.isfinite(value) for value in (*current, *targets, *speeds)):
            raise PlannerError("all joint values must be finite")
        if any(speed <= 0 for speed in speeds):
            raise PlannerError("all angular speeds must be positive")
        return max(abs(target - position) / speed for position, target, speed in zip(current, targets, speeds))
