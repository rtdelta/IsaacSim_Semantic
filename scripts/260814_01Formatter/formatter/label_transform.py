from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

from .models import LabelTransformResult


def transform_label_file(
    *,
    category: str,
    source: Path,
    destination: Path,
) -> LabelTransformResult:
    try:
        content = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"label is not valid UTF-8: {source}: {exc}") from exc

    output_lines: list[str] = []
    original_classes: Counter[int] = Counter()
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        parts = raw_line.split()
        if len(parts) != 5:
            raise ValueError(
                f"invalid YOLO column count in {source} line {line_number}: "
                f"expected 5, found {len(parts)}"
            )
        try:
            class_id = int(parts[0], 10)
        except ValueError as exc:
            raise ValueError(
                f"invalid class ID in {source} line {line_number}: {parts[0]!r}"
            ) from exc
        if class_id < 0:
            raise ValueError(
                f"negative class ID in {source} line {line_number}: {class_id}"
            )
        for coordinate_index, coordinate in enumerate(parts[1:], start=1):
            try:
                numeric = float(coordinate)
            except ValueError as exc:
                raise ValueError(
                    f"invalid coordinate {coordinate_index} in {source} "
                    f"line {line_number}: {coordinate!r}"
                ) from exc
            if not math.isfinite(numeric):
                raise ValueError(
                    f"non-finite coordinate {coordinate_index} in {source} "
                    f"line {line_number}: {coordinate!r}"
                )
        original_classes[class_id] += 1
        output_lines.append("0 " + " ".join(parts[1:]))

    destination.parent.mkdir(parents=True, exist_ok=True)
    output_content = "\n".join(output_lines) + ("\n" if output_lines else "")
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(output_content)
    return LabelTransformResult(
        category=category,
        source=source,
        destination=destination,
        line_count=len(output_lines),
        empty=not output_lines,
        original_classes=dict(original_classes),
    )
