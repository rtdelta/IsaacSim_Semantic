from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from semantic_world_v03.config import MotionConfig
from semantic_world_v03.motion import CsvArticulationMotion


class MotionTests(unittest.TestCase):
    def test_csv_linear_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trajectory = root / "trajectory.csv"
            trajectory.write_text("time,boom\n0,0\n1,2\n", encoding="utf-8")
            driver = CsvArticulationMotion(
                MotionConfig(
                    driver="semantic_world_v03.motion:CsvArticulationMotion",
                    trajectory=str(trajectory),
                    settings={
                        "articulation_prim_path": "/World/Excavator",
                        "joint_columns": {"boom_joint": "boom"},
                        "interpolation": "linear",
                    },
                ),
                stage=None,
            )
            self.assertEqual(driver._values(0.5)["boom"], 1.0)
            self.assertEqual(driver._values(2.0)["boom"], 2.0)


if __name__ == "__main__":
    unittest.main()
