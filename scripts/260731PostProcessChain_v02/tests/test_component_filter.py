from __future__ import annotations

import unittest

import numpy as np

from postprocess_chain_v02.modules.component_filter.config import ComponentFilterConfig
from postprocess_chain_v02.modules.component_filter.module import (
    filter_connected_components,
)
from postprocess_chain_v02.modules.semantic_features.module import (
    extract_semantic_features,
)


class ComponentFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ComponentFilterConfig(
            enabled=True,
            connectivity=4,
            minimum_connected_component_pixels=5,
        )

    def test_removes_components_smaller_than_five_and_keeps_exactly_five(self) -> None:
        mask = np.zeros((8, 12), dtype=np.bool_)
        mask[0, 0:4] = True
        mask[3, 2:7] = True
        result = filter_connected_components(mask, self.config)
        self.assertEqual(result.raw_pixel_count, 9)
        self.assertEqual(result.clean_pixel_count, 5)
        self.assertEqual(result.kept_component_count, 1)
        self.assertEqual(result.removed_component_count, 1)
        self.assertEqual(result.removed_pixel_count, 4)
        self.assertFalse(result.mask[0, 0])
        self.assertTrue(result.mask[3, 2])

    def test_diagonal_pixels_are_not_connected_in_four_neighborhood(self) -> None:
        mask = np.eye(5, dtype=np.bool_)
        result = filter_connected_components(mask, self.config)
        self.assertEqual(result.raw_pixel_count, 5)
        self.assertEqual(result.clean_pixel_count, 0)
        self.assertEqual(result.removed_component_count, 5)

    def test_keeps_every_qualified_component_not_only_the_largest(self) -> None:
        mask = np.zeros((8, 14), dtype=np.bool_)
        mask[1, 1:6] = True
        mask[5, 7:13] = True
        result = filter_connected_components(mask, self.config)
        self.assertEqual(result.clean_pixel_count, 11)
        self.assertEqual(result.kept_component_count, 2)
        self.assertEqual(result.removed_component_count, 0)

    def test_different_semantic_labels_never_connect(self) -> None:
        semantic = np.zeros((4, 12), dtype=np.uint16)
        semantic[1, 1:5] = 1
        semantic[1, 5:10] = 2
        features = extract_semantic_features(
            semantic,
            (1, 2, 3, 4, 5),
            self.config,
        )
        np.testing.assert_array_equal(features.raw_counts, [4, 5, 0, 0, 0])
        np.testing.assert_array_equal(features.counts, [0, 5, 0, 0, 0])
        np.testing.assert_array_equal(features.removed_pixel_counts, [4, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
