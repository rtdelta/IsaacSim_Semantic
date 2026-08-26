from __future__ import annotations

from typing import Iterable, Tuple

from .pixel_box import PixelBox


def normalize_box(
    box: PixelBox,
    image_width: int,
    image_height: int,
) -> Tuple[float, float, float, float]:
    box.validate_inside(image_width, image_height)
    return (
        (box.left + box.right) / 2.0 / image_width,
        (box.top + box.bottom) / 2.0 / image_height,
        box.width / image_width,
        box.height / image_height,
    )


def format_yolo_line(
    class_id: int,
    box: PixelBox,
    image_width: int,
    image_height: int,
) -> str:
    if class_id < 0:
        raise ValueError("YOLO class ID must be non-negative")
    x_center, y_center, width, height = normalize_box(box, image_width, image_height)
    return f"{class_id} {x_center:.8f} {y_center:.8f} " f"{width:.8f} {height:.8f}"


def format_yolo_lines(lines: Iterable[str]) -> str:
    values = list(lines)
    return "\n".join(values) + ("\n" if values else "")
