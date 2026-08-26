from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

from .models import YoloAnnotation


def parse_yolo_file(
    path: Path,
    maximum_annotations: int = 0,
) -> Tuple[YoloAnnotation, ...]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read YOLO label file {path}: {exc}") from exc

    annotations = []
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        fields = raw_line.split()
        if len(fields) != 5:
            raise ValueError(
                f"{path}:{line_number} must contain five YOLO fields"
            )
        try:
            class_id = int(fields[0])
        except ValueError as exc:
            raise ValueError(
                f"{path}:{line_number} has an invalid class ID"
            ) from exc
        if class_id < 0 or str(class_id) != fields[0]:
            raise ValueError(
                f"{path}:{line_number} class ID must be a non-negative integer"
            )
        try:
            x_center, y_center, width, height = (
                float(value) for value in fields[1:]
            )
        except ValueError as exc:
            raise ValueError(
                f"{path}:{line_number} has invalid YOLO coordinates"
            ) from exc
        values = (x_center, y_center, width, height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(
                f"{path}:{line_number} contains non-finite coordinates"
            )
        if not 0.0 <= x_center <= 1.0 or not 0.0 <= y_center <= 1.0:
            raise ValueError(
                f"{path}:{line_number} center is outside [0, 1]"
            )
        if not 0.0 < width <= 1.0 or not 0.0 < height <= 1.0:
            raise ValueError(
                f"{path}:{line_number} size is outside (0, 1]"
            )
        annotations.append(
            YoloAnnotation(
                class_id=class_id,
                x_center=x_center,
                y_center=y_center,
                width=width,
                height=height,
                raw_line=raw_line,
                line_number=line_number,
            )
        )
    if maximum_annotations and len(annotations) > maximum_annotations:
        raise ValueError(
            f"{path} contains {len(annotations)} annotations; "
            f"maximum allowed is {maximum_annotations}"
        )
    return tuple(annotations)


def format_preserved_lines(annotations: Tuple[YoloAnnotation, ...]) -> str:
    if not annotations:
        return ""
    return "\n".join(item.raw_line for item in annotations) + "\n"
