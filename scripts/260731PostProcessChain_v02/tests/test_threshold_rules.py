from __future__ import annotations

import unittest

import numpy as np

from postprocess_chain_v02.modules.threshold_rules.config import (
    CollisionRuleConfig,
    SingleToothRuleConfig,
    ThresholdRulesConfig,
)
from postprocess_chain_v02.modules.threshold_rules.module import build_rule_masks

from tests.helpers import make_feature_matrix


class ThresholdRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ThresholdRulesConfig(
            enabled=True,
            single_tooth=SingleToothRuleConfig(0.5, 0.8, "x_over_y", 1.5, 3),
            collision_model=CollisionRuleConfig(0.5, 3),
        )

    def test_five_physical_teeth_are_always_counted(self) -> None:
        visibility = np.asarray(
            [
                [0.5, 0.49, -1.0, 1.0, 0.5],
                [0.49, 0.49, 0.49, 1.0, 1.0],
            ]
        )
        source = np.asarray(
            [
                [True, True, False, True, True],
                [True, True, False, True, True],
            ]
        )
        masks = build_rule_masks(
            make_feature_matrix(visibility, source=source), self.config
        )
        np.testing.assert_array_equal(masks.occlusion_bad_count, [2, 3])
        np.testing.assert_array_equal(masks.collision_keep, [True, False])
        np.testing.assert_array_equal(masks.single_bad_tooth_count, [2, 3])
        np.testing.assert_array_equal(masks.drop_all_single_boxes, [False, True])
        self.assertTrue(masks.single_keep[0, 0])
        self.assertFalse(masks.single_keep[0, 2])

    def test_three_bad_reference_poses_drop_collision_model(self) -> None:
        fill = np.asarray([[0.7, 0.7, 0.7, 0.9, 0.9]])
        masks = build_rule_masks(
            make_feature_matrix(np.ones((1, 5)), fill=fill), self.config
        )
        self.assertEqual(masks.pose_bad_count[0], 3)
        self.assertFalse(masks.collision_keep[0])

    def test_single_and_collision_frame_limits_are_independent(self) -> None:
        config = ThresholdRulesConfig(
            enabled=True,
            single_tooth=SingleToothRuleConfig(0.5, 0.8, "x_over_y", 1.5, 3),
            collision_model=CollisionRuleConfig(0.5, 4),
        )
        visibility = np.asarray([[0.4, 0.4, 0.4, 1.0, 1.0]])
        masks = build_rule_masks(make_feature_matrix(visibility), config)
        self.assertEqual(masks.single_bad_tooth_count[0], 3)
        self.assertTrue(masks.drop_all_single_boxes[0])
        self.assertFalse(masks.single_keep[0].any())
        self.assertEqual(masks.collision_bad_tooth_count[0], 3)
        self.assertTrue(masks.collision_keep[0])

    def test_ratio_uses_full_yolo_box_pixel_dimensions(self) -> None:
        features = make_feature_matrix(np.ones((1, 5)))
        features.full_axis_boxes[0] = np.asarray(
            [
                [0, 0, 6, 4],
                [0, 0, 5, 4],
                [0, 0, 8, 4],
                [0, 0, 4, 8],
                [0, 0, 3, 2],
            ],
            dtype=np.int32,
        )
        masks = build_rule_masks(features, self.config)
        np.testing.assert_allclose(
            masks.height_width_ratios[0],
            [1.5, 1.25, 2.0, 0.5, 1.5],
        )
        np.testing.assert_array_equal(
            masks.single_height_width_bad[0],
            [False, True, False, True, False],
        )

    def test_y_over_x_mode_uses_reciprocal_direction(self) -> None:
        config = ThresholdRulesConfig(
            enabled=True,
            single_tooth=SingleToothRuleConfig(0.5, 0.8, "y_over_x", 1.5, 3),
            collision_model=CollisionRuleConfig(0.5, 3),
        )
        features = make_feature_matrix(np.ones((1, 5)))
        features.full_axis_boxes[0, 0] = np.asarray([0, 0, 4, 8])
        masks = build_rule_masks(features, config)
        self.assertEqual(masks.height_width_ratios[0, 0], 2.0)
        self.assertFalse(masks.single_height_width_bad[0, 0])


if __name__ == "__main__":
    unittest.main()
