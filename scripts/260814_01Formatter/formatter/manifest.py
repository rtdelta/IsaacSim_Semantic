from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

from .models import FramePlan, RunConfig


def write_rename_manifest(path: Path, plans: Sequence[FramePlan]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "numeric_frame_id",
            "source_rgb_frame_id",
            "source_tooth_frame_id",
            "source_collision_frame_id",
            "normalized_frame_id",
            "source_rgb",
            "output_rgb",
            "source_tooth_label",
            "output_tooth_label",
            "source_collision_label",
            "output_collision_label",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for plan in plans:
            source = plan.source
            writer.writerow(
                {
                    "numeric_frame_id": source.numeric_frame_id,
                    "source_rgb_frame_id": source.rgb_frame_token,
                    "source_tooth_frame_id": source.tooth_frame_token,
                    "source_collision_frame_id": source.collision_frame_token,
                    "normalized_frame_id": plan.normalized_frame_id,
                    "source_rgb": source.rgb_path.name,
                    "output_rgb": plan.rgb_name,
                    "source_tooth_label": source.tooth_label_path.name,
                    "output_tooth_label": plan.tooth_label_name,
                    "source_collision_label": source.collision_label_path.name,
                    "output_collision_label": plan.collision_label_name,
                }
            )


def write_formatter_manifest(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def config_snapshot(config: RunConfig) -> Mapping[str, object]:
    return {
        "schema_version": config.schema_version,
        "input_root": str(config.input_root),
        "output_root": str(config.output_root),
        "filename_prefix": config.filename_prefix,
        "classes": {
            "tooth_class_name": config.classes.tooth_class_name,
            "collision_class_name": config.classes.collision_class_name,
        },
        "output": {
            "preserve_reports": config.output.preserve_reports,
            "unchanged_file_mode": config.output.unchanged_file_mode,
        },
        "performance": {
            "workers": config.performance.workers,
            "max_in_flight": config.performance.max_in_flight,
        },
    }
