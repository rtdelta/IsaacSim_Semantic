from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from postprocess_chain_v02.config import load_config
from postprocess_chain_v02.main_pipeline import run_pipeline

from tests.helpers import config_value, make_dataset, write_config


def _label_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*.txt"))
    }


class PipelineIntegrationTests(unittest.TestCase):
    def test_full_pipeline_outputs_three_sibling_directories_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            raw = config_value(root, inputs)
            config_path = write_config(root / "full.json", raw)
            manifest = run_pipeline(load_config(config_path))

            output = root / "output"
            dataset = output / "dataset"
            self.assertEqual(
                {item.name for item in dataset.iterdir()},
                {"rgb", "tooth_boxes", "tooth_collision_model"},
            )
            self.assertEqual(len(list((dataset / "rgb").glob("*.png"))), 2)
            self.assertEqual(
                (dataset / "rgb" / "rgb_0000.png").read_bytes(),
                (inputs["rgb"] / "rgb_0000.png").read_bytes(),
            )
            self.assertFalse(list((dataset / "tooth_boxes").glob("*.png")))
            self.assertFalse(list((dataset / "tooth_collision_model").glob("*.png")))
            self.assertEqual(
                len(
                    (dataset / "tooth_boxes" / "rgb_0000.txt").read_text().splitlines()
                ),
                5,
            )
            self.assertEqual(
                (dataset / "tooth_collision_model" / "rgb_0001.txt").read_text(),
                "",
            )
            self.assertEqual(
                (dataset / "tooth_collision_model" / "rgb_0000.txt").read_text(),
                "0 0.46250000 0.30000000 0.80000000 0.10000000\n",
            )
            self.assertTrue((output / "reports" / "frame_summary.csv").is_file())
            with (output / "reports" / "tooth_decisions.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                first_decision = next(csv.DictReader(handle))
            self.assertEqual(first_decision["box_x_length"], "8")
            self.assertEqual(first_decision["box_y_length"], "4")
            self.assertEqual(first_decision["height_width_axis_mode"], "x_over_y")
            self.assertEqual(float(first_decision["height_width_ratio"]), 2.0)
            self.assertEqual(first_decision["height_width_pass"], "True")
            self.assertEqual(first_decision["single_bad_tooth_count"], "0")
            self.assertEqual(first_decision["drop_all_single_boxes"], "False")
            self.assertNotIn("oriented_aspect_ratio", first_decision)
            with (output / "reports" / "tooth_features.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                feature_rows = list(csv.DictReader(handle))
            noisy_row = next(
                row
                for row in feature_rows
                if row["frame_id"] == "0001" and row["class_id"] == "2"
            )
            self.assertEqual(noisy_row["full_raw_pixels"], "1")
            self.assertEqual(noisy_row["whole_pixels"], "0")
            self.assertEqual(noisy_row["full_removed_pixels"], "1")
            self.assertTrue((root / "cache" / "features_cache.npz").is_file())
            self.assertFalse(manifest["cache"]["used"])

    def test_threshold_change_reuses_analysis_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            first = config_value(root, inputs, "output_first")
            first_path = write_config(root / "first.json", first)
            run_pipeline(load_config(first_path))

            second = config_value(root, inputs, "output_second")
            second["pipeline"]["mode"] = "filter_only"
            second["modules"]["threshold_rules"]["single_tooth"][
                "minimum_visible_ratio_a"
            ] = 0.9
            second_path = write_config(root / "second.json", second)
            manifest = run_pipeline(load_config(second_path))
            self.assertTrue(manifest["cache"]["used"])
            self.assertNotEqual(
                json.loads((root / "output_first" / "manifest.json").read_text())[
                    "run_fingerprint"
                ],
                manifest["run_fingerprint"],
            )

    def test_axis_mode_change_reuses_cache_and_changes_filter_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            first = config_value(root, inputs, "output_x_over_y")
            run_pipeline(load_config(write_config(root / "x_over_y.json", first)))

            second = config_value(root, inputs, "output_y_over_x")
            second["pipeline"]["mode"] = "filter_only"
            second["modules"]["threshold_rules"]["single_tooth"][
                "height_width_axis_mode"
            ] = "y_over_x"
            manifest = run_pipeline(
                load_config(write_config(root / "y_over_x.json", second))
            )

            self.assertTrue(manifest["cache"]["used"])
            self.assertEqual(
                (
                    root
                    / "output_y_over_x"
                    / "dataset"
                    / "tooth_boxes"
                    / "rgb_0000.txt"
                ).read_text(),
                "",
            )

    def test_component_filter_change_invalidates_analysis_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            first = config_value(root, inputs, "output_min_5")
            run_pipeline(load_config(write_config(root / "min_5.json", first)))

            second = config_value(root, inputs, "output_min_6")
            second["modules"]["component_filter"][
                "minimum_connected_component_pixels"
            ] = 6
            manifest = run_pipeline(
                load_config(write_config(root / "min_6.json", second))
            )
            self.assertFalse(manifest["cache"]["used"])

    def test_parallel_worker_counts_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            raw_one = config_value(root, inputs, "output_one", workers=1)
            raw_one["cache"]["enabled"] = False
            raw_one["cache"]["reuse"] = False
            run_pipeline(load_config(write_config(root / "one.json", raw_one)))

            raw_two = config_value(root, inputs, "output_two", workers=2)
            raw_two["cache"]["enabled"] = False
            raw_two["cache"]["reuse"] = False
            run_pipeline(load_config(write_config(root / "two.json", raw_two)))
            self.assertEqual(
                _label_snapshot(root / "output_one" / "dataset"),
                _label_snapshot(root / "output_two" / "dataset"),
            )


if __name__ == "__main__":
    unittest.main()
