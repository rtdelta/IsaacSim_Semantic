from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from joint_position_recorder.trajectory_recorder import ActualAngleRecorder, RecorderError


JOINTS = ("cab", "boom", "small_arm", "bucket")


def test_recorder_publishes_csv_and_metadata_atomically(tmp_path: Path) -> None:
    output = tmp_path / "angles.csv"
    recorder = ActualAngleRecorder(output, JOINTS)
    recorder.start((0.0, 1.0, 2.0, 3.0), {"control_mode": "direct_position"})
    assert recorder.partial_path.exists()
    assert not output.exists()

    recorder.record(0.1, (0.8, 1.5, 1.5, 3.2))
    published = recorder.stop({"result": "completed"})

    assert published == output.resolve()
    assert output.exists()
    assert not recorder.partial_path.exists()
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["time", *JOINTS]
    assert rows[-1] == ["0.100000000", "0.800000000", "1.500000000", "1.500000000", "3.200000000"]
    metadata = json.loads(recorder.metadata_path.read_text(encoding="utf-8"))
    assert metadata["sample_count"] == 2
    assert metadata["completed"] is True
    assert metadata["joint_order"] == list(JOINTS)


def test_recorder_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "angles.csv"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(RecorderError, match="Refusing to overwrite"):
        ActualAngleRecorder(output, JOINTS).start((0.0, 0.0, 0.0, 0.0))


def test_abort_retains_partial_file(tmp_path: Path) -> None:
    recorder = ActualAngleRecorder(tmp_path / "angles.csv", JOINTS)
    recorder.start((0.0, 0.0, 0.0, 0.0))

    partial = recorder.abort()

    assert partial is not None
    assert partial.exists()
    assert not recorder.output_path.exists()
