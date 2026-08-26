from __future__ import annotations

import unittest

import numpy as np

from postprocess_chain_v02.modules.component_filter.config import ComponentFilterConfig
from postprocess_chain_v02.modules.semantic_features.module import (
    boxes_to_array,
    extract_semantic_features,
)


class SemanticFeatureTests(unittest.TestCase):
    def test_extracts_five_counts_and_half_open_boxes(self) -> None:
        semantic = np.zeros((8, 12), dtype=np.uint16)
        semantic[1:3, 2:5] = 10
        semantic[4:5, 7:9] = 12
        features = extract_semantic_features(semantic, (10, 11, 12, 13, 14))
        np.testing.assert_array_equal(features.counts, [6, 0, 2, 0, 0])
        boxes, valid = boxes_to_array(features)
        np.testing.assert_array_equal(boxes[0], [2, 1, 5, 3])
        np.testing.assert_array_equal(boxes[2], [7, 4, 9, 5])
        np.testing.assert_array_equal(valid, [True, False, True, False, False])

    def test_component_cleanup_prevents_outlier_from_expanding_box(self) -> None:
        semantic = np.zeros((10, 12), dtype=np.uint16)
        semantic[4:6, 4:7] = 10
        semantic[0, 0] = 10
        features = extract_semantic_features(
            semantic,
            (10, 11, 12, 13, 14),
            ComponentFilterConfig(True, 4, 5),
        )
        target = features.targets[0]
        self.assertEqual(target.raw_pixel_count, 7)
        self.assertEqual(target.pixel_count, 6)
        self.assertEqual(target.removed_pixel_count, 1)
        self.assertEqual(target.box.as_tuple(), (4, 4, 7, 6))


if __name__ == "__main__":
    unittest.main()
