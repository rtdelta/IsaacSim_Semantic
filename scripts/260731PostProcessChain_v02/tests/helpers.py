from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
from PIL import Image

from postprocess_chain_v02.models import FeatureMatrix


LABELS = tuple(f"teeth_{index:02d}_front_3DGS" for index in range(1, 6))


def make_feature_matrix(
    visibility: np.ndarray,
    fill: np.ndarray | None = None,
    aspect: np.ndarray | None = None,
    source: np.ndarray | None = None,
) -> FeatureMatrix:
    visibility = np.asarray(visibility, dtype=np.float64)
    if visibility.ndim != 2 or visibility.shape[1] != 5:
        raise ValueError("visibility must have shape (F, 5)")
    frames = visibility.shape[0]
    fill = (
        np.full((frames, 5), 0.9, dtype=np.float64)
        if fill is None
        else np.asarray(fill, dtype=np.float64)
    )
    aspect = (
        np.full((frames, 5), 2.0, dtype=np.float64)
        if aspect is None
        else np.asarray(aspect, dtype=np.float64)
    )
    source = (
        np.ones((frames, 5), dtype=np.bool_)
        if source is None
        else np.asarray(source, dtype=np.bool_)
    )
    statuses = np.full((frames, 5), "valid", dtype="<U20")
    statuses[visibility < 0] = "reference_missing"
    boxes = np.tile(
        np.asarray(
            [
                [1, 1, 5, 3],
                [6, 1, 10, 3],
                [11, 1, 15, 3],
                [16, 1, 20, 3],
                [21, 1, 25, 3],
            ],
            dtype=np.int32,
        ),
        (frames, 1, 1),
    )
    return FeatureMatrix(
        frame_ids=tuple(f"{index:04d}" for index in range(frames)),
        image_widths=np.full(frames, 32, dtype=np.int32),
        image_heights=np.full(frames, 16, dtype=np.int32),
        whole_raw_counts=np.full((frames, 5), 8, dtype=np.int64),
        whole_counts=np.full((frames, 5), 8, dtype=np.int64),
        reference_raw_counts=np.full((frames, 5), 8, dtype=np.int64),
        reference_counts=np.full((frames, 5), 8, dtype=np.int64),
        full_kept_component_counts=np.ones((frames, 5), dtype=np.int32),
        full_removed_component_counts=np.zeros((frames, 5), dtype=np.int32),
        full_removed_pixel_counts=np.zeros((frames, 5), dtype=np.int64),
        reference_kept_component_counts=np.ones((frames, 5), dtype=np.int32),
        reference_removed_component_counts=np.zeros((frames, 5), dtype=np.int32),
        reference_removed_pixel_counts=np.zeros((frames, 5), dtype=np.int64),
        visibility_ratios=visibility,
        ratio_statuses=statuses,
        full_axis_boxes=boxes.copy(),
        reference_axis_boxes=boxes.copy(),
        full_geometry_valid=np.ones((frames, 5), dtype=np.bool_),
        reference_geometry_valid=np.ones((frames, 5), dtype=np.bool_),
        reference_fill_ratios=fill,
        reference_aspect_ratios=aspect,
        reference_angles=np.zeros((frames, 5), dtype=np.float64),
        reference_pose_statuses=np.full((frames, 5), "valid", dtype="<U24"),
        source_box_exists=source,
    )


def make_dataset(root: Path) -> Dict[str, Path]:
    rgb = root / "input" / "full_rgb"
    full = root / "input" / "full_semantic"
    reference = root / "input" / "reference_semantic"
    for directory in (rgb, full, reference):
        directory.mkdir(parents=True, exist_ok=True)

    height, width = 40, 80
    reference_array = np.zeros((height, width), dtype=np.uint16)
    rectangles = []
    for index, semantic_id in enumerate(range(1, 6)):
        left = 5 + index * 14
        right = left + 8
        top = 10
        bottom = 14
        reference_array[top:bottom, left:right] = semantic_id
        rectangles.append((left, top, right, bottom))

    full_frame_0 = reference_array.copy()
    full_frame_1 = np.zeros_like(reference_array)
    for semantic_id, (left, top, right, bottom) in zip(range(1, 3), rectangles[:2]):
        full_frame_1[top:bottom, left:right] = semantic_id
    for semantic_id, (left, top, _, _) in zip(range(3, 6), rectangles[2:]):
        full_frame_1[top, left] = semantic_id

    for frame_id, full_array in (
        ("0000", full_frame_0),
        ("0001", full_frame_1),
    ):
        Image.new("RGB", (width, height), color=(30, 60, 90)).save(
            rgb / f"rgb_{frame_id}.png"
        )
        np.save(full / f"semantic_id_{frame_id}.npy", full_array)
        np.save(reference / f"semantic_id_{frame_id}.npy", reference_array)

    mapping = root / "input" / "semantic_mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_dtype": "uint16",
                "classes": [
                    {"id": index, "label": label}
                    for index, label in enumerate(LABELS, start=1)
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"rgb": rgb, "full": full, "reference": reference, "mapping": mapping}


def config_value(
    root: Path,
    inputs: Dict[str, Path],
    output_name: str = "output",
    workers: int = 2,
) -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "pipeline": {
            "mode": "full",
            "strict_pairing": True,
            "on_frame_error": "fail_fast",
        },
        "inputs": {
            "full_scene": {
                "rgb_dir": str(inputs["rgb"]),
                "semantic_dir": str(inputs["full"]),
            },
            "reference": {
                "capture_variant": "front_teeth_only",
                "semantic_dir": str(inputs["reference"]),
            },
            "semantic_mapping": str(inputs["mapping"]),
        },
        "targets": {
            "teeth": [
                {
                    "class_id": index,
                    "class_name": f"tooth_{index + 1:02d}",
                    "semantic_label": label,
                }
                for index, label in enumerate(LABELS)
            ],
            "collision_model": {
                "class_id": 0,
                "class_name": "tooth_collision_model",
            },
        },
        "modules": {
            "semantic_features": {
                "enabled": True,
                "target_extraction": "single_target_scan",
            },
            "component_filter": {
                "enabled": True,
                "connectivity": 4,
                "minimum_connected_component_pixels": 5,
            },
            "visibility_ratio": {
                "enabled": True,
                "zero_reference_value": -1,
                "ratio_over_one": "keep_and_flag",
            },
            "pose_metrics": {
                "enabled": True,
                "algorithm": "pixel_cell_min_area_rect_v1",
                "invalid_value": -1,
                "write_angle": True,
            },
            "single_tooth_boxes": {
                "enabled": True,
                "minimum_pixels": 1,
            },
            "threshold_rules": {
                "enabled": True,
                "single_tooth": {
                    "minimum_visible_ratio_a": 0.5,
                    "minimum_fill_ratio_c": 0.8,
                    "height_width_axis_mode": "x_over_y",
                    "minimum_height_width_ratio_d": 1.5,
                    "drop_all_single_boxes_if_bad_teeth_at_least": 3,
                },
                "collision_model": {
                    "minimum_visible_ratio_b": 0.5,
                    "drop_collision_box_if_bad_teeth_at_least": 3,
                },
            },
            "collision_box": {
                "enabled": True,
                "length_axis": "x",
                "length_source": "full_scene",
                "width_source": "reference",
                "union_scope": "all_valid_teeth",
            },
        },
        "execution": {
            "backend": "numpy_opencv",
            "workers": workers,
            "max_in_flight": max(2, workers),
            "reader_threads": 1,
            "verification_level": "full",
            "verification_sample_frames": 2,
        },
        "cache": {
            "enabled": True,
            "reuse": True,
            "directory": str(root / "cache"),
            "fingerprint_mode": "metadata",
            "on_mismatch": "rebuild",
        },
        "output": {
            "root": str(root / output_name),
            "overwrite": False,
            "image_mode": "copy",
            "keep_empty_label_files": True,
            "staging_mode": "atomic_directory",
        },
        "reporting": {"level": "full"},
    }


def write_config(path: Path, value: Dict[str, Any]) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
