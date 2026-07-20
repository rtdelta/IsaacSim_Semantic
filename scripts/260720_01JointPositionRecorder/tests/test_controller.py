from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

from joint_position_recorder.config import load_project_config
from joint_position_recorder.controller import MotionController, MotionState


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeAdapter:
    def __init__(self, positions: Sequence[float]) -> None:
        self.positions = tuple(float(value) for value in positions)
        self.ready = True
        self.write_history: list[tuple[float, ...]] = []

    def get_positions_degrees(self) -> tuple[float, ...]:
        return self.positions

    def set_positions_degrees(self, positions_degrees: Sequence[float]) -> None:
        self.positions = tuple(float(value) for value in positions_degrees)
        self.write_history.append(self.positions)

    def hold_current_position(self) -> tuple[float, ...]:
        self.write_history.append(self.positions)
        return self.positions


@pytest.fixture
def configured_controller() -> tuple[MotionController, FakeAdapter]:
    config = load_project_config(
        PROJECT_ROOT / "profiles" / "excavator_four_joint_default.json"
    )
    adapter = FakeAdapter((0.0, 0.0, 0.0, 0.0))
    limits = {
        "cab": (-178.0, 178.0),
        "boom": (-33.0, 68.0),
        "small_arm": (-78.0, 68.0),
        "bucket": (-88.0, 78.0),
    }
    controller = MotionController(config, adapter, limits)
    controller.synchronize()
    return controller, adapter


def test_controller_moves_all_joints_independently(configured_controller) -> None:
    controller, adapter = configured_controller
    controller.start_motion(
        {"cab": 1.0, "boom": 1.0, "small_arm": -1.0, "bucket": 0.5},
        {"cab": 2.0, "boom": 4.0, "small_arm": 1.0, "bucket": 1.0},
    )

    first = controller.update(0.25)
    assert first.state is MotionState.MOVING
    assert tuple(first.current_degrees.values()) == pytest.approx((0.1, 0.2, -0.05, 0.05))

    for _ in range(19):
        final = controller.update(0.05)

    assert final.state is MotionState.REACHED
    assert tuple(final.current_degrees.values()) == pytest.approx((1.0, 1.0, -1.0, 0.5))
    assert adapter.positions == pytest.approx((1.0, 1.0, -1.0, 0.5))


def test_controller_clamps_large_frame_dt(configured_controller) -> None:
    controller, _ = configured_controller
    controller.start_motion(
        {"cab": 10.0, "boom": 0.0, "small_arm": 0.0, "bucket": 0.0},
        {"cab": 8.0, "boom": 5.0, "small_arm": 5.0, "bucket": 5.0},
    )

    snapshot = controller.update(1.0)

    assert snapshot.current_degrees["cab"] == pytest.approx(0.4)


def test_stop_holds_read_back_position(configured_controller) -> None:
    controller, adapter = configured_controller
    controller.start_motion(
        {"cab": 10.0, "boom": 0.0, "small_arm": 0.0, "bucket": 0.0},
        {"cab": 8.0, "boom": 5.0, "small_arm": 5.0, "bucket": 5.0},
    )
    controller.update(0.05)

    snapshot = controller.stop_motion()

    assert snapshot.state is MotionState.IDLE
    assert snapshot.target_degrees == snapshot.current_degrees
    assert adapter.positions == pytest.approx((0.4, 0.0, 0.0, 0.0))


def test_target_must_be_inside_safe_limits(configured_controller) -> None:
    controller, _ = configured_controller

    with pytest.raises(ValueError, match="outside safe range"):
        controller.start_motion(
            {"cab": 179.0, "boom": 0.0, "small_arm": 0.0, "bucket": 0.0},
            {"cab": 8.0, "boom": 5.0, "small_arm": 5.0, "bucket": 5.0},
        )


def test_controller_records_adapter_read_back(tmp_path: Path, configured_controller) -> None:
    controller, adapter = configured_controller
    output = tmp_path / "actual.csv"
    controller.start_recording(output, {"test": True})
    adapter.positions = (1.0, 2.0, 3.0, 4.0)

    controller.update(0.02)
    controller.stop_recording()

    rows = output.read_text(encoding="utf-8").splitlines()
    assert rows[-1] == "0.020000000,1.000000000,2.000000000,3.000000000,4.000000000"
