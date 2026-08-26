from __future__ import annotations

import unittest

import numpy as np

from postprocess_chain_v02.modules.visibility_ratio.config import VisibilityRatioConfig
from postprocess_chain_v02.modules.visibility_ratio.module import calculate_visibility


class VisibilityRatioTests(unittest.TestCase):
    def test_reference_zero_is_negative_one_and_flagged(self) -> None:
        ratios, statuses = calculate_visibility(
            np.asarray([5, 0, 9, 3, 2]),
            np.asarray([10, 0, 3, 3, 4]),
            VisibilityRatioConfig(True, -1.0, "keep_and_flag"),
        )
        np.testing.assert_allclose(ratios, [0.5, -1.0, 3.0, 1.0, 0.5])
        self.assertEqual(statuses[1], "reference_missing")
        self.assertEqual(statuses[2], "ratio_over_one")
        self.assertEqual(statuses[0], "valid")


if __name__ == "__main__":
    unittest.main()
