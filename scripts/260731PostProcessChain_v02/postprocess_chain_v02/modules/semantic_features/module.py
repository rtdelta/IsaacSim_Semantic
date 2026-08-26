from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

from ...common.pixel_box import PixelBox
from ..component_filter.config import ComponentFilterConfig
from ..component_filter.module import filter_connected_components
from .models import SceneFeatures, TargetGeometry


def extract_semantic_features(
    semantic: np.ndarray,
    target_ids: Sequence[int],
    component_filter: ComponentFilterConfig | None = None,
) -> SceneFeatures:
    if semantic.ndim != 2:
        raise ValueError(f"semantic array must be 2D, got shape={semantic.shape}")
    if len(target_ids) != 5 or len(set(int(value) for value in target_ids)) != 5:
        raise ValueError("target_ids must contain five distinct IDs")

    targets = []
    for semantic_id in target_ids:
        raw_mask = semantic == int(semantic_id)
        if component_filter is None:
            raw_pixel_count = int(np.count_nonzero(raw_mask))
            clean_mask = raw_mask
            kept_component_count = 1 if raw_pixel_count else 0
            removed_component_count = 0
            removed_pixel_count = 0
        else:
            result = filter_connected_components(raw_mask, component_filter)
            raw_pixel_count = result.raw_pixel_count
            clean_mask = result.mask
            kept_component_count = result.kept_component_count
            removed_component_count = result.removed_component_count
            removed_pixel_count = result.removed_pixel_count
        y_values, x_values = np.nonzero(clean_mask)
        pixel_count = int(x_values.size)
        if pixel_count == 0:
            targets.append(
                TargetGeometry(
                    pixel_count=0,
                    box=None,
                    coordinates=np.empty((0, 2), dtype=np.int32),
                    raw_pixel_count=raw_pixel_count,
                    kept_component_count=kept_component_count,
                    removed_component_count=removed_component_count,
                    removed_pixel_count=removed_pixel_count,
                )
            )
            continue
        x_values = np.asarray(x_values, dtype=np.int32)
        y_values = np.asarray(y_values, dtype=np.int32)
        coordinates = np.column_stack((x_values, y_values)).astype(np.int32, copy=False)
        targets.append(
            TargetGeometry(
                pixel_count=pixel_count,
                box=PixelBox(
                    left=int(x_values.min()),
                    top=int(y_values.min()),
                    right=int(x_values.max()) + 1,
                    bottom=int(y_values.max()) + 1,
                ),
                coordinates=coordinates,
                raw_pixel_count=raw_pixel_count,
                kept_component_count=kept_component_count,
                removed_component_count=removed_component_count,
                removed_pixel_count=removed_pixel_count,
            )
        )
    return SceneFeatures(targets=tuple(targets))


def boxes_to_array(features: SceneFeatures) -> Tuple[np.ndarray, np.ndarray]:
    boxes = np.full((5, 4), -1, dtype=np.int32)
    valid = np.zeros(5, dtype=np.bool_)
    for index, target in enumerate(features.targets):
        if target.box is None:
            continue
        boxes[index] = np.asarray(target.box.as_tuple(), dtype=np.int32)
        valid[index] = True
    return boxes, valid
