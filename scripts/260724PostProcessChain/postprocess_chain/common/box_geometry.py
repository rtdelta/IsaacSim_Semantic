from __future__ import annotations

from typing import Mapping, Sequence, Tuple

import numpy as np

from .models import PixelBox, SemanticBox


def extract_semantic_boxes(
    semantic: np.ndarray,
    labels_to_ids: Mapping[str, int],
) -> Tuple[SemanticBox, ...]:
    if not labels_to_ids:
        return ()

    target_ids = tuple(labels_to_ids.values())
    target_mask = np.isin(semantic, target_ids)
    all_y, all_x = np.nonzero(target_mask)
    if not all_x.size:
        return ()
    values = np.asarray(semantic[all_y, all_x])

    boxes = []
    for label, semantic_id in labels_to_ids.items():
        selected = values == semantic_id
        pixel_count = int(np.count_nonzero(selected))
        if pixel_count == 0:
            continue
        x_values = all_x[selected]
        y_values = all_y[selected]
        boxes.append(
            SemanticBox(
                semantic_label=label,
                semantic_id=semantic_id,
                pixel_count=pixel_count,
                box=PixelBox(
                    left=int(x_values.min()),
                    top=int(y_values.min()),
                    right=int(x_values.max()) + 1,
                    bottom=int(y_values.max()) + 1,
                ),
            )
        )
    return tuple(boxes)


def select_image_extrema(
    boxes: Sequence[SemanticBox],
) -> Tuple[SemanticBox, SemanticBox]:
    if len(boxes) < 2:
        raise ValueError("at least two boxes are required to select image extrema")
    left = min(boxes, key=lambda item: (item.box.left, item.box.center_x))
    right = max(boxes, key=lambda item: (item.box.right, item.box.center_x))
    if left is right:
        ordered = sorted(boxes, key=lambda item: item.box.center_x)
        left, right = ordered[0], ordered[-1]
    return left, right


def envelope_from_endpoint_boxes(first: PixelBox, second: PixelBox) -> PixelBox:
    return PixelBox(
        left=min(first.left, second.left),
        top=min(first.top, second.top),
        right=max(first.right, second.right),
        bottom=max(first.bottom, second.bottom),
    )
