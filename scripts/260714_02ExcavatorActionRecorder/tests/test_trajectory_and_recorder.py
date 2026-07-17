"""Pure-Python tests for trajectory recording and playback compatibility."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from excavator_gui_recorder import RecorderGuiConfig
from joint_trajectory_recorder import (
    TrajectoryRecorder,
    resolve_csv_path,
    validate_csv_filename,
)
from trajectory import JOINT_NAMES, JointTrajectory


HOME_TARGETS = {
    "cab": -2.4,
    "boom": -8.0,
    "small_arm": 29.666664,
    "bucket": -8.833334,
}


class RecorderTests(unittest.TestCase):
    def test_records_valid_existing_player_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "manual.csv"
            recorder = TrajectoryRecorder(path)
            recorder.start(HOME_TARGETS)
            second = dict(HOME_TARGETS)
            second["cab"] = 1.5
            recorder.record_sample(1.0 / 60.0, second)
            final_path = recorder.stop()

            self.assertEqual(final_path, path.resolve())
            trajectory = JointTrajectory.from_csv(path)
            self.assertEqual(len(trajectory.keyframes), 2)
            self.assertAlmostEqual(trajectory.keyframes[1].targets["cab"], 1.5)
            self.assertFalse(recorder.partial_path.exists())

    def test_refuses_to_overwrite_existing_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "manual.csv"
            path.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                TrajectoryRecorder(path).start(HOME_TARGETS)

    def test_abort_keeps_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "manual.csv"
            recorder = TrajectoryRecorder(path)
            recorder.start(HOME_TARGETS)
            partial = recorder.abort()
            self.assertEqual(partial, recorder.partial_path)
            self.assertTrue(recorder.partial_path.exists())
            self.assertFalse(path.exists())

    def test_rejects_non_increasing_record_times(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            recorder = TrajectoryRecorder(Path(temporary_directory) / "manual.csv")
            recorder.start(HOME_TARGETS)
            with self.assertRaisesRegex(ValueError, "strictly increasing"):
                recorder.record_sample(0.0, HOME_TARGETS)
            recorder.abort()


class TrajectoryTests(unittest.TestCase):
    def _make_trajectory(self, directory: str) -> JointTrajectory:
        path = Path(directory) / "playback.csv"
        path.write_text(
            "time,cab,boom,small_arm,bucket\n"
            "0.0,-2.4,-8.0,29.0,-8.0\n"
            "1.0,7.6,2.0,19.0,12.0\n"
            "2.0,-2.4,-8.0,29.0,-8.0\n",
            encoding="utf-8",
        )
        return JointTrajectory.from_csv(path)

    def test_linear_interpolation_and_hold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            trajectory = self._make_trajectory(temporary_directory)
            _, targets = trajectory.sample(0.5, "hold")
            self.assertAlmostEqual(targets["cab"], 2.6)
            _, final_targets = trajectory.sample(10.0, "hold")
            self.assertAlmostEqual(final_targets["cab"], -2.4)

    def test_loop_wraps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            trajectory = self._make_trajectory(temporary_directory)
            trajectory_time, targets = trajectory.sample(2.5, "loop")
            self.assertAlmostEqual(trajectory_time, 0.5)
            self.assertAlmostEqual(targets["cab"], 2.6)

    def test_csv_columns_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.csv"
            path.write_text("time,cab\n0,0\n1,1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "columns"):
                JointTrajectory.from_csv(path)


class InputParameterTests(unittest.TestCase):
    def test_path_and_filename_are_separate_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            resolved = resolve_csv_path(temporary_directory, "action_01.csv")
            self.assertEqual(resolved.name, "action_01.csv")
            self.assertEqual(resolved.parent, Path(temporary_directory).resolve())

    def test_filename_rejects_path_traversal(self) -> None:
        for invalid in ("../action.csv", "nested/action.csv", "action.txt", ""):
            with self.subTest(filename=invalid):
                with self.assertRaises(ValueError):
                    validate_csv_filename(invalid)

    def test_gui_config_preserves_record_mode(self) -> None:
        config = RecorderGuiConfig(
            csv_directory=Path("trajectories"),
            csv_filename="action.csv",
            recording_enabled=True,
        ).validated()
        self.assertTrue(config.recording_enabled)
        self.assertEqual(tuple(JOINT_NAMES), ("cab", "boom", "small_arm", "bucket"))


if __name__ == "__main__":
    unittest.main()

