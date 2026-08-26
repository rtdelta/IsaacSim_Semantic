from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pytest

from joint_position_recorder.config import load_project_config
from joint_position_recorder.controller import MotionController, MotionState
from joint_position_recorder.trajectory_recorder import RecordingState


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


def test_pause_excludes_time_and_resume_records_actual_position(
    tmp_path: Path, configured_controller
) -> None:
    controller, adapter = configured_controller
    output = tmp_path / "actual.csv"
    controller.start_recording(output, {"test": True})
    adapter.positions = (1.0, 2.0, 3.0, 4.0)
    controller.update(0.02)

    paused = controller.pause_recording()
    adapter.positions = (10.0, 20.0, 30.0, 40.0)
    during_pause = controller.update(1.0)

    assert paused.recording_state is RecordingState.PAUSED
    assert during_pause.recording
    assert during_pause.recorded_samples == 2
    assert during_pause.recording_elapsed_seconds == pytest.approx(0.02)
    assert during_pause.excluded_pause_duration_seconds == pytest.approx(0.05)
    assert tuple(during_pause.current_degrees.values()) == pytest.approx(adapter.positions)

    controller.resume_recording()
    adapter.positions = (11.0, 21.0, 31.0, 41.0)
    resumed = controller.update(0.03)
    controller.stop_recording()

    assert resumed.recording_state is RecordingState.RECORDING
    assert resumed.recorded_samples == 3
    rows = output.read_text(encoding="utf-8").splitlines()
    assert rows[-2] == "0.020000000,1.000000000,2.000000000,3.000000000,4.000000000"
    assert rows[-1] == "0.050000000,11.000000000,21.000000000,31.000000000,41.000000000"
    metadata = json.loads(output.with_name("actual.metadata.json").read_text(encoding="utf-8"))
    assert metadata["pause_count"] == 1
    assert metadata["excluded_pause_duration_seconds"] == pytest.approx(0.05)
    assert metadata["trajectory_duration_seconds"] == pytest.approx(0.05)
    assert metadata["recording_time_policy"] == "exclude_paused_intervals"
    assert metadata["position_priority"] == "actual_readback_no_interpolation"


def test_motion_continues_while_recording_is_paused(
    tmp_path: Path, configured_controller
) -> None:
    controller, adapter = configured_controller
    controller.start_recording(tmp_path / "actual.csv", {})
    controller.pause_recording()
    controller.start_motion(
        {"cab": 1.0, "boom": 1.0, "small_arm": -1.0, "bucket": 0.5},
        {"cab": 2.0, "boom": 4.0, "small_arm": 1.0, "bucket": 1.0},
    )

    snapshot = controller.update(0.05)

    assert snapshot.state is MotionState.MOVING
    assert snapshot.recording_state is RecordingState.PAUSED
    assert snapshot.recorded_samples == 1
    assert adapter.positions == pytest.approx((0.1, 0.2, -0.05, 0.05))
    controller.abort_recording()


def test_paused_controller_rejects_new_start_and_can_publish(
    tmp_path: Path, configured_controller
) -> None:
    controller, _ = configured_controller
    output = tmp_path / "actual.csv"
    controller.start_recording(output, {})
    controller.update(0.02)
    controller.pause_recording()

    with pytest.raises(RuntimeError, match="already active"):
        controller.start_recording(tmp_path / "other.csv", {})

    published = controller.stop_recording()

    assert published == output.resolve()
    snapshot = controller.snapshot()
    assert snapshot.recording_state is RecordingState.IDLE
    assert not snapshot.recording
    assert snapshot.recording_elapsed_seconds == 0.0
