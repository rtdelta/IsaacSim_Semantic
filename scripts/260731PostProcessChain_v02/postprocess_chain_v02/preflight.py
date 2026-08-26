from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

from .common.semantic_mapping import (
    load_semantic_mapping,
    mapping_sha256,
    resolve_target_ids,
)
from .config import RunConfig
from .frame_discovery import discover_frame_tasks
from .models import InputContract


def _inspect_array(path: Path) -> Tuple[Tuple[int, int], np.dtype]:
    array = np.load(path, mmap_mode="r", allow_pickle=False)
    try:
        if array.ndim != 2:
            raise ValueError(f"semantic array must be 2D: {path}")
        if not np.issubdtype(array.dtype, np.integer):
            raise ValueError(f"semantic array must use integer dtype: {path}")
        return (int(array.shape[0]), int(array.shape[1])), array.dtype
    finally:
        del array


def _contains_or_equals(parent: Path, child: Path) -> bool:
    return parent == child or parent in child.parents


def run_preflight(config: RunConfig) -> InputContract:
    for path, description in (
        (config.inputs.full_scene.rgb_dir, "full-scene RGB directory"),
        (config.inputs.full_scene.semantic_dir, "full-scene semantic directory"),
        (
            config.inputs.reference.semantic_dir,
            f"{config.inputs.reference.capture_variant} reference semantic directory",
        ),
    ):
        if not path.is_dir():
            raise FileNotFoundError(f"{description} does not exist: {path}")
    if not config.inputs.semantic_mapping.is_file():
        raise FileNotFoundError(
            f"semantic mapping does not exist: {config.inputs.semantic_mapping}"
        )

    input_paths = (
        config.inputs.full_scene.rgb_dir,
        config.inputs.full_scene.semantic_dir,
        config.inputs.reference.semantic_dir,
    )
    for input_path in input_paths:
        if _contains_or_equals(input_path, config.output.root) or _contains_or_equals(
            config.output.root, input_path
        ):
            raise ValueError(
                "output root must not equal, contain, or be contained by an input directory"
            )
        if _contains_or_equals(
            input_path, config.cache.directory
        ) or _contains_or_equals(config.cache.directory, input_path):
            raise ValueError(
                "cache directory must not equal, contain, or be contained by an input directory"
            )
    if _contains_or_equals(
        config.output.root, config.cache.directory
    ) or _contains_or_equals(config.cache.directory, config.output.root):
        raise ValueError(
            "output root and cache directory must not equal or contain each other"
        )
    if config.output.root.exists() and not config.output.overwrite:
        raise FileExistsError(f"output root already exists: {config.output.root}")

    mapping = load_semantic_mapping(config.inputs.semantic_mapping)
    labels = tuple(target.semantic_label for target in config.targets.teeth)
    target_ids = resolve_target_ids(mapping, labels)
    tasks = discover_frame_tasks(config)
    full_shape, full_dtype = _inspect_array(tasks[0].full_semantic_path)
    reference_shape, reference_dtype = _inspect_array(tasks[0].reference_semantic_path)
    if full_shape != reference_shape:
        raise ValueError(
            f"first-frame semantic shape mismatch: full={full_shape}, "
            f"reference={reference_shape}"
        )
    if full_dtype != reference_dtype:
        raise ValueError(
            f"first-frame semantic dtype mismatch: full={full_dtype}, "
            f"reference={reference_dtype}"
        )
    if mapping.expected_dtype and full_dtype != np.dtype(mapping.expected_dtype):
        raise ValueError(
            f"semantic dtype={full_dtype}, mapping declares {mapping.expected_dtype}"
        )
    dtype_limits = np.iinfo(full_dtype)
    invalid_target_ids = [
        value
        for value in target_ids
        if value < dtype_limits.min or value > dtype_limits.max
    ]
    if invalid_target_ids:
        raise ValueError(
            f"target semantic IDs {invalid_target_ids} cannot be represented by "
            f"semantic dtype {full_dtype}"
        )
    with Image.open(tasks[0].full_rgb_path) as image:
        image_width, image_height = image.size
    if full_shape != (image_height, image_width):
        raise ValueError(
            f"semantic shape={full_shape} does not match RGB size="
            f"({image_width}, {image_height})"
        )
    return InputContract(
        tasks=tasks,
        target_ids=target_ids,
        expected_dtype=str(full_dtype),
        shape=full_shape,
        mapping_sha256=mapping_sha256(config.inputs.semantic_mapping),
    )
