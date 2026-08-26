from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

from .models import FramePlan


def _file_names(directory: Path, *, skip_classes: bool) -> set[str]:
    values: set[str] = set()
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file(follow_symlinks=False):
                raise ValueError(f"unexpected non-file in output dataset: {entry.path}")
            if skip_classes and entry.name == "classes.txt":
                continue
            values.add(entry.name)
    return values


def validate_staging_dataset(
    *,
    staging_root: Path,
    plans: Sequence[FramePlan],
    filename_prefix: str,
    padding_width: int,
    tooth_class_name: str,
    collision_class_name: str,
    label_statistics: Mapping[str, Mapping[str, object]],
) -> None:
    dataset = staging_root / "dataset"
    rgb_dir = dataset / "rgb"
    tooth_dir = dataset / "tooth_boxes"
    collision_dir = dataset / "tooth_collision_model"

    expected_rgb = {plan.rgb_name for plan in plans}
    expected_tooth = {plan.tooth_label_name for plan in plans}
    expected_collision = {plan.collision_label_name for plan in plans}
    actual_rgb = _file_names(rgb_dir, skip_classes=False)
    actual_tooth = _file_names(tooth_dir, skip_classes=True)
    actual_collision = _file_names(collision_dir, skip_classes=True)
    if actual_rgb != expected_rgb:
        raise ValueError(
            f"output RGB file set mismatch: expected {len(expected_rgb)}, "
            f"found {len(actual_rgb)}"
        )
    if actual_tooth != expected_tooth:
        raise ValueError(
            f"output tooth label set mismatch: expected {len(expected_tooth)}, "
            f"found {len(actual_tooth)}"
        )
    if actual_collision != expected_collision:
        raise ValueError(
            f"output collision label set mismatch: expected {len(expected_collision)}, "
            f"found {len(actual_collision)}"
        )

    rgb_stems = {Path(value).stem for value in actual_rgb}
    tooth_stems = {Path(value).stem for value in actual_tooth}
    collision_stems = {Path(value).stem for value in actual_collision}
    if rgb_stems != tooth_stems or rgb_stems != collision_stems:
        raise ValueError("output RGB and label stems do not match")

    for plan in plans:
        if len(plan.normalized_frame_id) != padding_width:
            raise ValueError(
                f"incorrect normalized frame width: {plan.normalized_frame_id}"
            )
        expected_stem = f"{filename_prefix}_{plan.normalized_frame_id}"
        if (
            Path(plan.rgb_name).stem != expected_stem
            or Path(plan.tooth_label_name).stem != expected_stem
            or Path(plan.collision_label_name).stem != expected_stem
        ):
            raise ValueError(f"output stem does not follow naming rule: {expected_stem}")

    expected_tooth_classes = tooth_class_name + "\n"
    expected_collision_classes = collision_class_name + "\n"
    if (tooth_dir / "classes.txt").read_text(encoding="utf-8") != expected_tooth_classes:
        raise ValueError("tooth_boxes/classes.txt validation failed")
    if (
        collision_dir / "classes.txt"
    ).read_text(encoding="utf-8") != expected_collision_classes:
        raise ValueError("tooth_collision_model/classes.txt validation failed")

    for category in ("tooth", "collision"):
        stats = label_statistics.get(category)
        if stats is None:
            raise ValueError(f"missing label statistics for {category}")
        if int(stats["files"]) != len(plans):
            raise ValueError(
                f"label output count mismatch for {category}: "
                f"{stats['files']} != {len(plans)}"
            )
        if int(stats["nonzero_output_class_lines"]) != 0:
            raise ValueError(f"non-zero output classes found in {category} labels")
