from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from formatter.config import load_config
from formatter.pipeline import run_formatter
from tests.helpers import make_source, write_config


class PipelineIntegrationTests(unittest.TestCase):
    def test_formats_complete_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0", "0001", "9999", "10000"])
            output = root / "Formatted"
            config_path = write_config(
                root / "config.json", input_root=source, output_root=output
            )
            summary = run_formatter(load_config(config_path))

            expected_stems = {
                "Sim_Fangshan_tooth_260813_00000",
                "Sim_Fangshan_tooth_260813_00001",
                "Sim_Fangshan_tooth_260813_09999",
                "Sim_Fangshan_tooth_260813_10000",
            }
            rgb = output / "dataset" / "rgb"
            tooth = output / "dataset" / "tooth_boxes"
            collision = output / "dataset" / "tooth_collision_model"
            self.assertEqual({path.stem for path in rgb.glob("*.png")}, expected_stems)
            self.assertEqual(
                {path.stem for path in tooth.glob("*.txt") if path.name != "classes.txt"},
                expected_stems,
            )
            self.assertEqual(
                {
                    path.stem
                    for path in collision.glob("*.txt")
                    if path.name != "classes.txt"
                },
                expected_stems,
            )
            for directory in (tooth, collision):
                for path in directory.glob("*.txt"):
                    if path.name == "classes.txt":
                        continue
                    for line in path.read_text(encoding="utf-8").splitlines():
                        self.assertEqual(line.split()[0], "0")

            self.assertEqual(
                (tooth / "classes.txt").read_text(encoding="utf-8"), "tooth\n"
            )
            self.assertEqual(
                (collision / "classes.txt").read_text(encoding="utf-8"),
                "tooth_collision_model\n",
            )
            self.assertEqual(
                (output / "reports" / "frame_summary.csv").read_text(
                    encoding="utf-8"
                ),
                "frame_id,class_id\n0000,4\n",
            )
            self.assertTrue((output / "source_manifest.json").is_file())
            self.assertTrue((output / "rename_manifest.csv").is_file())
            manifest = json.loads(
                (output / "formatter_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["naming"]["padding_width"], 5)
            self.assertEqual(manifest["frames"], 4)
            self.assertEqual(summary["padding_width"], 5)
            self.assertEqual(summary["label_lines_rewritten"], 4)

            self.assertTrue(
                (source / "dataset" / "rgb" / "rgb_0001.png").is_file()
            )
            self.assertFalse((source / "formatter_manifest.json").exists())

    def test_failure_removes_staging_and_leaves_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0"])
            bad_label = source / "dataset" / "tooth_boxes" / "rgb_0.txt"
            bad_label.write_text("4 nan 0.2 0.3 0.4\n", encoding="utf-8")
            output = root / "Formatted"
            config_path = write_config(
                root / "config.json", input_root=source, output_root=output
            )
            with self.assertRaisesRegex(ValueError, "non-finite coordinate"):
                run_formatter(load_config(config_path))
            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".Formatted.staging-*")))


if __name__ == "__main__":
    unittest.main()
