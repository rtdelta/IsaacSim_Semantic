from __future__ import annotations

import numpy as np

from ...models import FeatureMatrix, RuleMasks
from .config import ThresholdRulesConfig


def calculate_height_width_ratios(
    features: FeatureMatrix,
    axis_mode: str,
) -> np.ndarray:
    """Calculate directional ratios from the exact full-scene YOLO source boxes."""
    boxes = np.asarray(features.full_axis_boxes, dtype=np.float64)
    x_lengths = boxes[:, :, 2] - boxes[:, :, 0]
    y_lengths = boxes[:, :, 3] - boxes[:, :, 1]
    valid = features.full_geometry_valid & (x_lengths > 0.0) & (y_lengths > 0.0)
    ratios = np.full(x_lengths.shape, -1.0, dtype=np.float64)
    if axis_mode == "x_over_y":
        numerator, denominator = x_lengths, y_lengths
    elif axis_mode == "y_over_x":
        numerator, denominator = y_lengths, x_lengths
    else:
        raise ValueError(f"unsupported height/width axis mode: {axis_mode}")
    ratios[valid] = numerator[valid] / denominator[valid]
    return ratios


def build_rule_masks(
    features: FeatureMatrix,
    config: ThresholdRulesConfig,
) -> RuleMasks:
    single = config.single_tooth
    collision = config.collision_model
    visibility_invalid = features.visibility_ratios < 0.0
    fill_invalid = features.reference_fill_ratios < 0.0
    height_width_ratios = calculate_height_width_ratios(
        features,
        single.height_width_axis_mode,
    )
    height_width_invalid = height_width_ratios < 0.0

    single_visibility_bad = visibility_invalid | (
        features.visibility_ratios < single.minimum_visible_ratio_a
    )
    single_fill_bad = fill_invalid | (
        features.reference_fill_ratios < single.minimum_fill_ratio_c
    )
    single_height_width_bad = height_width_invalid | (
        height_width_ratios < single.minimum_height_width_ratio_d
    )
    single_tooth_bad = (
        ~features.source_box_exists
        | single_visibility_bad
        | single_fill_bad
        | single_height_width_bad
    )
    single_bad_tooth_count = single_tooth_bad.sum(axis=1, dtype=np.int16)
    drop_all_single_boxes = (
        single_bad_tooth_count
        >= single.drop_all_single_boxes_if_bad_teeth_at_least
    )
    single_drop = features.source_box_exists & (
        single_visibility_bad | single_fill_bad | single_height_width_bad
        | drop_all_single_boxes[:, np.newaxis]
    )
    single_keep = features.source_box_exists & ~single_drop

    collision_visibility_bad = visibility_invalid | (
        features.visibility_ratios < collision.minimum_visible_ratio_b
    )
    pose_bad = (
        fill_invalid
        | height_width_invalid
        | (features.reference_fill_ratios < single.minimum_fill_ratio_c)
        | (height_width_ratios < single.minimum_height_width_ratio_d)
    )
    occlusion_bad_count = collision_visibility_bad.sum(axis=1, dtype=np.int16)
    pose_bad_count = pose_bad.sum(axis=1, dtype=np.int16)
    collision_tooth_bad = (
        ~features.source_box_exists | collision_visibility_bad | pose_bad
    )
    collision_bad_tooth_count = collision_tooth_bad.sum(axis=1, dtype=np.int16)
    collision_drop = (
        collision_bad_tooth_count
        >= collision.drop_collision_box_if_bad_teeth_at_least
    )
    return RuleMasks(
        height_width_ratios=np.asarray(height_width_ratios, dtype=np.float64),
        single_visibility_bad=np.asarray(single_visibility_bad, dtype=np.bool_),
        single_fill_bad=np.asarray(single_fill_bad, dtype=np.bool_),
        single_height_width_bad=np.asarray(
            single_height_width_bad, dtype=np.bool_
        ),
        single_tooth_bad=np.asarray(single_tooth_bad, dtype=np.bool_),
        single_bad_tooth_count=np.asarray(single_bad_tooth_count, dtype=np.int16),
        drop_all_single_boxes=np.asarray(drop_all_single_boxes, dtype=np.bool_),
        single_drop=np.asarray(single_drop, dtype=np.bool_),
        single_keep=np.asarray(single_keep, dtype=np.bool_),
        collision_visibility_bad=np.asarray(collision_visibility_bad, dtype=np.bool_),
        pose_bad=np.asarray(pose_bad, dtype=np.bool_),
        occlusion_bad_count=np.asarray(occlusion_bad_count, dtype=np.int16),
        pose_bad_count=np.asarray(pose_bad_count, dtype=np.int16),
        collision_tooth_bad=np.asarray(collision_tooth_bad, dtype=np.bool_),
        collision_bad_tooth_count=np.asarray(
            collision_bad_tooth_count, dtype=np.int16
        ),
        collision_drop=np.asarray(collision_drop, dtype=np.bool_),
        collision_keep=np.asarray(~collision_drop, dtype=np.bool_),
    )
