from __future__ import annotations

from typing import Iterable

import numpy as np

from ...common.pixel_box import PixelBox, union_boxes
from ...models import CollisionBoxResult
from .config import CollisionBoxConfig


def _valid_boxes(values: np.ndarray, valid: np.ndarray) -> Iterable[PixelBox]:
    for index in range(5):
        if bool(valid[index]):
            yield PixelBox.from_values(values[index])


def build_collision_box(
    frame_id: str,
    full_boxes: np.ndarray,
    reference_boxes: np.ndarray,
    full_valid: np.ndarray,
    reference_valid: np.ndarray,
    collision_keep: bool,
    image_width: int,
    image_height: int,
    config: CollisionBoxConfig,
) -> CollisionBoxResult:
    full_union = union_boxes(_valid_boxes(full_boxes, full_valid))
    reference_union = union_boxes(_valid_boxes(reference_boxes, reference_valid))
    if not collision_keep:
        return CollisionBoxResult(
            frame_id=frame_id,
            box=None,
            mixed_geometry_valid=full_union is not None and reference_union is not None,
            action="drop",
            reason="threshold rules rejected the collision model",
            full_union=full_union,
            reference_union=reference_union,
        )
    if full_union is None or reference_union is None:
        return CollisionBoxResult(
            frame_id=frame_id,
            box=None,
            mixed_geometry_valid=False,
            action="drop",
            reason="mixed geometry is unavailable",
            full_union=full_union,
            reference_union=reference_union,
        )
    if config.length_axis == "y":
        box = PixelBox(
            left=reference_union.left,
            top=full_union.top,
            right=reference_union.right,
            bottom=full_union.bottom,
        )
    else:
        box = PixelBox(
            left=full_union.left,
            top=reference_union.top,
            right=full_union.right,
            bottom=reference_union.bottom,
        )
    box.validate_inside(image_width, image_height)
    return CollisionBoxResult(
        frame_id=frame_id,
        box=box,
        mixed_geometry_valid=True,
        action="keep",
        reason="threshold rules passed and mixed geometry is valid",
        full_union=full_union,
        reference_union=reference_union,
    )
