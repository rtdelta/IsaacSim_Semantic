from __future__ import annotations

import pytest

from joint_position_recorder.motion_planner import ConstantSpeedPlanner, PlannerError


def test_step_moves_in_both_directions_at_requested_speed() -> None:
    result = ConstantSpeedPlanner().step(
        current_degrees=(0.0, 10.0),
        target_degrees=(10.0, -10.0),
        speed_degrees_per_second=(4.0, 8.0),
        dt=0.25,
    )

    assert result.positions_degrees == pytest.approx((1.0, 8.0))
    assert result.reached == (False, False)


def test_step_clamps_final_sample_without_overshoot() -> None:
    result = ConstantSpeedPlanner().step(
        current_degrees=(9.9, -9.9),
        target_degrees=(10.0, -10.0),
        speed_degrees_per_second=(5.0, 5.0),
        dt=0.1,
    )

    assert result.positions_degrees == (10.0, -10.0)
    assert result.all_reached


def test_expected_duration_uses_slowest_finishing_joint() -> None:
    duration = ConstantSpeedPlanner.expected_duration_seconds(
        current_degrees=(0.0, 0.0, 0.0, 0.0),
        target_degrees=(8.0, 20.0, -10.0, 1.0),
        speed_degrees_per_second=(8.0, 5.0, 5.0, 1.0),
    )

    assert duration == pytest.approx(4.0)


@pytest.mark.parametrize("dt", [0.0, -0.1, float("nan")])
def test_step_rejects_invalid_dt(dt: float) -> None:
    with pytest.raises(PlannerError, match="dt must be positive"):
        ConstantSpeedPlanner().step((0.0,), (1.0,), (1.0,), dt)
