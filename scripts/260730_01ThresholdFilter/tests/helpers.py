from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Sequence, Tuple

import numpy as np


LABELS = (
    "tooth_1_front_3DGS",
    "tooth_2_front_3DGS",
    "tooth_3_front_3DGS",
    "tooth_4_front_3DGS",
    "tooth_5_front_3DGS",
)
GROUP_NAME = "tooth_front_group"


def _write_json(path: Path, value: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def yolo_line(class_id: int, index: int) -> str:
    return (
        f"{class_id} {0.1 + index * 0.1:.6f} 0.500000 "
        "0.050000 0.050000"
    )


def create_dataset(
    root: Path,
    identity_mode: str = "legacy_zero_class_order",
    ratio_input_format: str = "counts_cache_npz",
    output_name: str = "filtered",
    workers: int = 2,
    frame_count: int = 3,
) -> Tuple[Path, Path, Path]:
    if frame_count < 3:
        raise ValueError("synthetic dataset requires at least three frames")
    post_root = root / "post"
    ratio_root = root / "ratio"
    output_root = root / output_name
    tooth_dir = post_root / "modules" / "tooth_boxes"
    group_dir = post_root / "modules" / "tooth_group"
    tooth_dir.mkdir(parents=True)
    group_dir.mkdir(parents=True)
    (tooth_dir / "classes.txt").write_text("tooth\n", encoding="utf-8")
    (group_dir / "classes.txt").write_text("tooth_group\n", encoding="utf-8")

    width = max(4, len(str(frame_count - 1)))
    frame_ids = tuple(
        f"{frame_index:0{width}d}" for frame_index in range(frame_count)
    )
    whole = np.full((frame_count, 5), 10, dtype=np.uint32)
    whole[1] = np.asarray([10, 2, 10, 2, 2], dtype=np.uint32)
    whole[2] = np.asarray([10, 0, 10, 10, 10], dtype=np.uint32)
    reference = np.full((frame_count, 5), 10, dtype=np.uint32)
    for frame_index, frame_id in enumerate(frame_ids):
        lines = []
        for target_index, count in enumerate(whole[frame_index]):
            if count < 1:
                continue
            class_id = (
                0
                if identity_mode == "legacy_zero_class_order"
                else target_index + 1
            )
            lines.append(yolo_line(class_id, target_index))
        (tooth_dir / f"rgb_{frame_id}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )
        (group_dir / f"rgb_{frame_id}.txt").write_text(
            yolo_line(0, 0) + "\n",
            encoding="utf-8",
        )
        (tooth_dir / f"rgb_{frame_id}.png").write_bytes(b"synthetic-image")
        (group_dir / f"rgb_{frame_id}.png").write_bytes(b"synthetic-image")

    semantic_path = "/dataset/full_scene/semantic_id"
    mapping_path = "/dataset/semantic_mapping.json"
    _write_json(
        post_root / "manifest.json",
        {
            "schema_version": 1,
            "status": "completed",
            "inputs": {
                "semantic_dir": semantic_path,
                "semantic_mapping": mapping_path,
            },
            "modules": ["tooth_boxes", "tooth_group"],
        },
    )
    ratio_root.mkdir(parents=True)
    _write_json(
        ratio_root / "manifest.json",
        {
            "schema_version": 1,
            "status": "completed",
            "inputs": {
                "whole_scene_semantic_dir": semantic_path,
                "excavator_only_semantic_dir": "/dataset/reference/semantic_id",
                "semantic_mapping": mapping_path,
            },
            "targets": [
                {"label": label, "semantic_id": index + 1}
                for index, label in enumerate(LABELS)
            ],
            "group_name": GROUP_NAME,
        },
    )
    np.savez(
        ratio_root / "counts_cache.npz",
        ordinals=np.arange(frame_count, dtype=np.int64),
        frame_ids=np.asarray(frame_ids, dtype=np.str_),
        whole_counts=whole,
        reference_counts=reference,
    )
    with (ratio_root / "per_frame.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        fieldnames = (
            "frame_id",
            "target",
            "whole_pixels",
            "reference_pixels",
            "pixel_ratio",
            "status",
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for frame_index, frame_id in enumerate(frame_ids):
            for target_index, label in enumerate(LABELS):
                ratio = whole[frame_index, target_index] / 10
                writer.writerow(
                    {
                        "frame_id": frame_id,
                        "target": label,
                        "whole_pixels": int(whole[frame_index, target_index]),
                        "reference_pixels": 10,
                        "pixel_ratio": format(float(ratio), ".12g"),
                        "status": "valid",
                    }
                )
            writer.writerow(
                {
                    "frame_id": frame_id,
                    "target": GROUP_NAME,
                    "whole_pixels": int(whole[frame_index].sum()),
                    "reference_pixels": 50,
                    "pixel_ratio": format(
                        float(whole[frame_index].sum() / 50), ".12g"
                    ),
                    "status": "valid",
                }
            )

    config = {
        "schema_version": 1,
        "inputs": {
            "postprocess": {
                "output_root": str(post_root),
                "manifest": "manifest.json",
                "tooth_module_dir": "modules/tooth_boxes",
                "group_module_dir": "modules/tooth_group",
            },
            "pixel_ratio": {
                "output_root": str(ratio_root),
                "manifest": "manifest.json",
                "input_format": ratio_input_format,
                "counts_cache": "counts_cache.npz",
                "per_frame_csv": "per_frame.csv",
            },
        },
        "targets": {
            "labels_in_physical_order": list(LABELS),
            "group_name": GROUP_NAME,
        },
        "identity": {
            "mode": identity_mode,
            "legacy_zero_class_order": {
                "source_class_id": 0,
                "source_min_pixels": 1,
            },
            "class_id_map": {
                "mapping": {
                    str(index + 1): label
                    for index, label in enumerate(LABELS)
                }
            },
        },
        "rules": {
            "single_tooth": {"minimum_visible_ratio": 0.5},
            "tooth_group": {
                "minimum_visible_ratio": 0.5,
                "minimum_low_teeth": 3,
            },
        },
        "ratio_handling": {
            "reference_missing": "error",
            "empty_ratio": "error",
            "ratio_over_one": "use_raw",
        },
        "execution": {
            "workers": workers,
            "max_in_flight": max(workers, 4),
            "on_error": "fail_fast",
            "dry_run": False,
            "staging_mode": "atomic_directory",
        },
        "performance": {
            "vectorized_rules": True,
            "directory_scan": "single_pass",
            "durability": "run_level",
            "verification_level": "full",
            "verification_sample_frames": 3,
        },
        "output": {
            "root": str(output_root),
            "overwrite": False,
            "image_mode": "hardlink_required",
            "keep_empty_label_files": True,
        },
        "reporting": {"level": "full"},
    }
    config_path = root / f"{output_name}.json"
    _write_json(config_path, config)
    return config_path, output_root, ratio_root
