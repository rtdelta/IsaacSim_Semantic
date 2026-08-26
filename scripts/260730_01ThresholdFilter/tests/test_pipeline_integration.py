from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from threshold_filter.config import load_config
from threshold_filter.pipeline import run_pipeline
from tests.helpers import create_dataset


class PipelineIntegrationTests(unittest.TestCase):
    def _run_mode(self, root: Path, mode: str, output_name: str) -> Path:
        config_path, output_root, _ = create_dataset(
            root,
            identity_mode=mode,
            output_name=output_name,
            workers=2,
        )
        summary = run_pipeline(load_config(config_path))
        self.assertEqual(summary["frames"], 3)
        self.assertEqual(summary["tooth_boxes"]["source"], 14)
        self.assertEqual(summary["tooth_boxes"]["dropped"], 3)
        self.assertEqual(summary["group_boxes"]["dropped"], 1)
        return output_root

    def test_legacy_and_class_id_modes_produce_expected_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_output = self._run_mode(
                root / "legacy_dataset",
                "legacy_zero_class_order",
                "legacy_output",
            )
            class_output = self._run_mode(
                root / "class_dataset",
                "class_id_map",
                "class_output",
            )

            legacy_frame = (
                legacy_output
                / "modules"
                / "tooth_boxes"
                / "rgb_0001.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(len(legacy_frame.splitlines()), 2)
            group_frame = (
                legacy_output
                / "modules"
                / "tooth_group"
                / "rgb_0001.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(group_frame, "")

            missing_middle = (
                legacy_output
                / "modules"
                / "tooth_boxes"
                / "rgb_0002.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(len(missing_middle.splitlines()), 4)

            class_frame = (
                class_output
                / "modules"
                / "tooth_boxes"
                / "rgb_0001.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(
                [line.split()[0] for line in class_frame.splitlines()],
                ["1", "3"],
            )
            manifest = json.loads(
                (class_output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["identity_mode"], "class_id_map")
            self.assertTrue((class_output / "decisions.csv").is_file())
            self.assertTrue((class_output / "frame_summary.csv").is_file())


if __name__ == "__main__":
    unittest.main()
