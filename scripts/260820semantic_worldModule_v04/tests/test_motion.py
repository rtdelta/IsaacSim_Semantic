import tempfile
import unittest
from pathlib import Path

from semantic_world_v04.core.models import MotionSpec
from semantic_world_v04.runtime.motion import CsvArticulationMotion, CsvTrajectory


class CsvTrajectoryTests(unittest.TestCase):
    def _trajectory(self, temp: str) -> Path:
        path = Path(temp) / "trajectory.csv"
        path.write_text(
            "time,joint_a,joint_b\n"
            "0.0,0.0,10.0\n"
            "1.0,2.0,20.0\n"
            "2.0,4.0,40.0\n",
            encoding="utf-8",
        )
        return path

    def test_linear_interpolation_and_clamping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trajectory = CsvTrajectory(
                self._trajectory(temp),
                time_column="time",
                required_columns=["joint_a", "joint_b"],
            )
            self.assertEqual(0.0, trajectory.sample(-1)["joint_a"])
            self.assertEqual(1.0, trajectory.sample(0.5)["joint_a"])
            self.assertEqual(4.0, trajectory.sample(99)["joint_a"])

    def test_hold_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trajectory = CsvTrajectory(
                self._trajectory(temp),
                time_column="time",
                required_columns=["joint_a"],
                interpolation="hold",
            )
            self.assertEqual(0.0, trajectory.sample(0.5)["joint_a"])

    def test_missing_column_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "missing columns"):
                CsvTrajectory(
                    self._trajectory(temp),
                    time_column="time",
                    required_columns=["does_not_exist"],
                )

    def test_csv_absolute_seek_requires_explicit_capability_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            options = {
                "articulation_prim_path": "/World/Robot",
                "joint_columns": {"joint_a": "joint_a"},
            }
            disabled = CsvArticulationMotion(
                MotionSpec(
                    plugin="csv_articulation",
                    source_path=str(self._trajectory(temp)),
                    supports_absolute_seek=False,
                    options=options,
                )
            )
            enabled = CsvArticulationMotion(
                MotionSpec(
                    plugin="csv_articulation",
                    source_path=str(self._trajectory(temp)),
                    supports_absolute_seek=True,
                    options=options,
                )
            )
            self.assertFalse(disabled.supports_absolute_seek)
            self.assertTrue(enabled.supports_absolute_seek)
            self.assertTrue(enabled.requires_physics)


if __name__ == "__main__":
    unittest.main()
