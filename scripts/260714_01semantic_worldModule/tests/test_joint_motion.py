"""Pure-Python tests for CSV trajectory loading and interpolation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from excavator_joint_motion import JointTrajectory


CSV_TEXT = """time,cab,boom,small_arm,bucket
0.0,-2.4,-8.0,29.0,-8.0
1.0,7.6,2.0,19.0,12.0
2.0,-2.4,-8.0,29.0,-8.0
"""


class JointTrajectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "trajectory.csv"
        self.path.write_text(CSV_TEXT, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loads_expected_keyframes(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        self.assertEqual(len(trajectory.keyframes), 3)
        self.assertAlmostEqual(trajectory.duration, 2.0)
        self.assertEqual(len(trajectory.sha256), 64)

    def test_linearly_interpolates_between_keyframes(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        trajectory_time, targets = trajectory.sample(0.5, "hold")
        self.assertAlmostEqual(trajectory_time, 0.5)
        self.assertAlmostEqual(targets["cab"], 2.6)
        self.assertAlmostEqual(targets["boom"], -3.0)
        self.assertAlmostEqual(targets["small_arm"], 24.0)
        self.assertAlmostEqual(targets["bucket"], 2.0)

    def test_loop_wraps_to_the_next_cycle(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        trajectory_time, targets = trajectory.sample(2.5, "loop")
        self.assertAlmostEqual(trajectory_time, 0.5)
        self.assertAlmostEqual(targets["cab"], 2.6)

    def test_hold_keeps_last_keyframe(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        trajectory_time, targets = trajectory.sample(5.0, "hold")
        self.assertAlmostEqual(trajectory_time, 2.0)
        self.assertAlmostEqual(targets["cab"], -2.4)

    def test_rejects_wrong_columns(self) -> None:
        self.path.write_text("time,cab\n0,0\n1,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "columns"):
            JointTrajectory.from_csv(self.path)

    def test_rejects_non_increasing_time(self) -> None:
        self.path.write_text(
            "time,cab,boom,small_arm,bucket\n0,0,0,0,0\n0,1,1,1,1\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            JointTrajectory.from_csv(self.path)


if __name__ == "__main__":
    unittest.main()
