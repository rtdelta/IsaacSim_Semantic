from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from threshold_filter.config import load_config
from threshold_filter.preflight import run_preflight
from threshold_filter.ratio_reader import load_ratio_matrix
from threshold_filter.rules import build_rule_masks
from tests.helpers import create_dataset


class RuleTests(unittest.TestCase):
    def test_single_and_group_boundaries_use_strictly_less_than(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path, _, _ = create_dataset(Path(temporary))
            config = load_config(config_path)
            contract = run_preflight(config)
            ratios = load_ratio_matrix(config, contract)
            masks = build_rule_masks(config, ratios)

            self.assertEqual(masks.single_drop[0].tolist(), [False] * 5)
            self.assertEqual(
                masks.single_drop[1].tolist(),
                [False, True, False, True, True],
            )
            self.assertEqual(masks.group_low_counts.tolist(), [0, 3, 1])
            self.assertEqual(masks.group_drop.tolist(), [False, True, False])


if __name__ == "__main__":
    unittest.main()
