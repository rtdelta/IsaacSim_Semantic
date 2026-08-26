from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conftest import config_payload, write_config
from semantic_world_v03.config import load_run_config
from semantic_world_v03.supervisor import plan_segments


class SupervisorPlanTests(unittest.TestCase):
    def test_variant_major_segment_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = config_payload(root / "out")
            payload["capture"]["variants"].append({"id": "isolated", "visibility": {}})
            config = load_run_config(write_config(root, payload))
            segments = plan_segments(config)
            self.assertEqual(
                [(item.variant_id, item.start_frame, item.end_frame) for item in segments],
                [
                    ("full_scene", 0, 5), ("full_scene", 5, 10),
                    ("full_scene", 10, 12), ("isolated", 0, 5),
                    ("isolated", 5, 10), ("isolated", 10, 12),
                ],
            )


if __name__ == "__main__":
    unittest.main()

