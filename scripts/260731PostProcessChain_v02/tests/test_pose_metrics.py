from __future__ import annotations

import unittest

import numpy as np

from postprocess_chain_v02.modules.pose_metrics.config import PoseMetricsConfig
from postprocess_chain_v02.modules.pose_metrics.module import calculate_pose_metrics
from postprocess_chain_v02.modules.semantic_features.module import (
    extract_semantic_features,
)


class PoseMetricTests(unittest.TestCase):
    def test_metrics_use_reference_mask_without_changing_image_axes(self) -> None:
        semantic = np.zeros((20, 30), dtype=np.uint16)
        semantic[5:9, 4:16] = 1
        reference = extract_semantic_features(semantic, (1, 2, 3, 4, 5))
        fill, aspect, angle, statuses = calculate_pose_metrics(
            reference,
            PoseMetricsConfig(True, "pixel_cell_min_area_rect_v1", -1.0, True),
        )
        self.assertAlmostEqual(fill[0], 1.0, places=6)
        self.assertAlmostEqual(aspect[0], 3.0, places=6)
        self.assertTrue(np.isfinite(angle[0]))
        self.assertEqual(statuses[0], "valid")
        np.testing.assert_array_equal(fill[1:], [-1.0] * 4)


if __name__ == "__main__":
    unittest.main()
