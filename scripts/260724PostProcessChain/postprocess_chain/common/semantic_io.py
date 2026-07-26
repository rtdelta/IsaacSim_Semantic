from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from PIL import Image

from .config_io import load_json_object
from .models import FrameTask, SemanticMapping


def load_semantic_mapping(path: Path) -> SemanticMapping:
    raw = load_json_object(path, "semantic mapping")
    classes = raw.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ValueError("semantic mapping.classes must be a non-empty array")

    label_to_id: Dict[str, int] = {}
    id_to_label: Dict[int, str] = {}
    for index, item in enumerate(classes):
        if not isinstance(item, dict):
            raise ValueError(f"semantic mapping.classes[{index}] must be an object")
        label = item.get("label")
        semantic_id = item.get("id")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"semantic mapping.classes[{index}].label must be a string")
        label = label.strip()
        if isinstance(semantic_id, bool) or not isinstance(semantic_id, int):
            raise ValueError(f"semantic mapping id for {label!r} must be an integer")
        if label in label_to_id:
            raise ValueError(f"duplicate semantic label: {label}")
        if semantic_id in id_to_label:
            raise ValueError(
                f"semantic id {semantic_id} is assigned to both "
                f"{id_to_label[semantic_id]!r} and {label!r}"
            )
        label_to_id[label] = semantic_id
        id_to_label[semantic_id] = label

    expected_dtype = str(raw.get("dataset_dtype", ""))
    if expected_dtype:
        try:
            np.dtype(expected_dtype)
        except TypeError as exc:
            raise ValueError(f"invalid semantic dataset_dtype: {expected_dtype}") from exc

    return SemanticMapping(label_to_id=label_to_id, expected_dtype=expected_dtype)


def load_frame_resources(
    task: FrameTask,
    expected_dtype: str,
) -> Tuple[np.ndarray, int, int]:
    semantic = np.load(task.semantic_path, mmap_mode="r", allow_pickle=False)
    if semantic.ndim != 2:
        raise ValueError(f"semantic array must be 2D, got shape={semantic.shape}")
    if expected_dtype and str(semantic.dtype) != expected_dtype:
        raise ValueError(
            f"semantic dtype={semantic.dtype}, mapping declares {expected_dtype}"
        )

    with Image.open(task.rgb_path) as image:
        image_width, image_height = image.size
    if semantic.shape != (image_height, image_width):
        raise ValueError(
            f"semantic shape={semantic.shape} does not match "
            f"RGB size=({image_width}, {image_height})"
        )
    return semantic, image_width, image_height
