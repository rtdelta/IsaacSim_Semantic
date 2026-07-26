from __future__ import annotations

import math
from typing import Tuple

from .models import PixelBox, YoloAnnotationSet


def normalize_box(
    box: PixelBox,
    image_width: int,
    image_height: int,
) -> Tuple[float, float, float, float]:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    if box.right > image_width or box.bottom > image_height:
        raise ValueError(
            f"box {box} exceeds image size ({image_width}, {image_height})"
        )

    values = (
        (box.left + box.right) / 2.0 / image_width,
        (box.top + box.bottom) / 2.0 / image_height,
        box.width / image_width,
        box.height / image_height,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("normalized box contains non-finite values")
    x_center, y_center, width, height = values
    if not (0.0 <= x_center <= 1.0 and 0.0 <= y_center <= 1.0):
        raise ValueError("normalized box center is outside [0, 1]")
    if not (0.0 < width <= 1.0 and 0.0 < height <= 1.0):
        raise ValueError("normalized box size is outside (0, 1]")
    return values


def format_annotation_set(
    annotation: YoloAnnotationSet,
    image_width: int,
    image_height: int,
    class_names: Tuple[str, ...],
) -> str:
    lines = []
    for detection in annotation.detections:
        if detection.class_id < 0 or detection.class_id >= len(class_names):
            raise ValueError(f"YOLO class id is out of range: {detection.class_id}")
        expected_name = class_names[detection.class_id]
        if detection.class_name != expected_name:
            raise ValueError(
                f"class id {detection.class_id} expects {expected_name!r}, "
                f"got {detection.class_name!r}"
            )
        x_center, y_center, width, height = normalize_box(
            detection.box,
            image_width,
            image_height,
        )
        lines.append(
            f"{detection.class_id} {x_center:.8f} {y_center:.8f} "
            f"{width:.8f} {height:.8f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")
