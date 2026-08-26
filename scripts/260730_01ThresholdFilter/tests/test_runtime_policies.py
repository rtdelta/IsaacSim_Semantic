from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from threshold_filter.config import load_config
from threshold_filter.models import RatioMatrix
from threshold_filter.pipeline import run_pipeline
from threshold_filter.rules import build_rule_masks
from tests.helpers import LABELS, create_dataset


class RuntimePolicyTests(unittest.TestCase):
    def test_reference_missing_errors_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path, _, _ = create_dataset(Path(temporary))
            config = load_config(config_path)
            shape = (1, 5)
            matrix = RatioMatrix(
                frame_ids=("0000",),
                labels=LABELS,
                whole_counts=np.zeros(shape, dtype=np.uint64),
                reference_counts=np.asarray(
                    [[0, 1, 1, 1, 1]], dtype=np.uint64
                ),
                ratios=np.asarray(
                    [[np.nan, 1.0, 1.0, 1.0, 1.0]], dtype=np.float64
                ),
                statuses=np.asarray(
                    [
                        [
                            "reference_missing",
                            "valid",
                            "valid",
                            "valid",
                            "valid",
                        ]
                    ],
                    dtype="<U20",
                ),
                source_backend="test",
            )
            with self.assertRaisesRegex(ValueError, "reference_missing"):
                build_rule_masks(config, matrix)

    def test_drop_policy_marks_invalid_tooth_low_for_both_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path, _, _ = create_dataset(Path(temporary))
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw["ratio_handling"]["reference_missing"] = "drop"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            config = load_config(config_path)
            shape = (1, 5)
            matrix = RatioMatrix(
                frame_ids=("0000",),
                labels=LABELS,
                whole_counts=np.zeros(shape, dtype=np.uint64),
                reference_counts=np.asarray(
                    [[0, 1, 1, 1, 1]], dtype=np.uint64
                ),
                ratios=np.asarray(
                    [[np.nan, 1.0, 1.0, 1.0, 1.0]], dtype=np.float64
                ),
                statuses=np.asarray(
                    [
                        [
                            "reference_missing",
                            "valid",
                            "valid",
                            "valid",
                            "valid",
                        ]
                    ],
                    dtype="<U20",
                ),
                source_backend="test",
            )
            masks = build_rule_masks(config, matrix)
            self.assertTrue(bool(masks.single_drop[0, 0]))
            self.assertTrue(bool(masks.group_low[0, 0]))
            self.assertFalse(bool(masks.group_drop[0]))

    def test_dry_run_writes_reports_without_module_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, output_root, _ = create_dataset(root)
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw["execution"]["dry_run"] = True
            raw["output"]["image_mode"] = "none"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            summary = run_pipeline(load_config(config_path))
            self.assertTrue(summary["dry_run"])
            self.assertTrue((output_root / "summary.json").is_file())
            self.assertTrue((output_root / "decisions.csv").is_file())
            self.assertFalse((output_root / "modules").exists())


if __name__ == "__main__":
    unittest.main()
