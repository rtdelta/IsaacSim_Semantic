from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Tuple

import numpy as np

from .models import DatasetContract, FramePair, SemanticMapping


def load_semantic_mapping(path: Path) -> SemanticMapping:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read semantic mapping: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("semantic mapping must contain a JSON object")
    classes = raw.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ValueError("semantic mapping.classes must be a non-empty array")

    label_to_id = {}
    used_ids = {}
    for index, item in enumerate(classes):
        if not isinstance(item, dict):
            raise ValueError(f"semantic mapping.classes[{index}] must be an object")
        label = item.get("label")
        semantic_id = item.get("id")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(
                f"semantic mapping.classes[{index}].label must be a string"
            )
        label = label.strip()
        if isinstance(semantic_id, bool) or not isinstance(semantic_id, int):
            raise ValueError(f"semantic ID for {label!r} must be an integer")
        if semantic_id < 0:
            raise ValueError(f"semantic ID for {label!r} must be non-negative")
        if label in label_to_id:
            raise ValueError(f"duplicate semantic label: {label}")
        if semantic_id in used_ids:
            raise ValueError(
                f"semantic ID {semantic_id} belongs to both "
                f"{used_ids[semantic_id]!r} and {label!r}"
            )
        label_to_id[label] = semantic_id
        used_ids[semantic_id] = label

    expected_dtype = str(raw.get("dataset_dtype", "")).strip()
    if expected_dtype:
        try:
            dtype = np.dtype(expected_dtype)
        except TypeError as exc:
            raise ValueError(
                f"semantic mapping has invalid dataset_dtype: {expected_dtype}"
            ) from exc
        if not np.issubdtype(dtype, np.integer):
            raise ValueError("semantic mapping dataset_dtype must be an integer dtype")

    return SemanticMapping(
        label_to_id=label_to_id,
        expected_dtype=expected_dtype,
    )


def mapping_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_target_ids(
    mapping: SemanticMapping,
    labels: Tuple[str, ...],
) -> Tuple[int, ...]:
    missing = [label for label in labels if label not in mapping.label_to_id]
    if missing:
        raise ValueError(
            "semantic mapping is missing target labels: " + ", ".join(missing)
        )
    target_ids = tuple(mapping.label_to_id[label] for label in labels)
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("target labels must resolve to distinct semantic IDs")
    return target_ids


def _inspect_array(path: Path) -> Tuple[Tuple[int, int], np.dtype]:
    array = np.load(path, mmap_mode="r", allow_pickle=False)
    try:
        if array.ndim != 2:
            raise ValueError(
                f"semantic array must be 2D: {path}, shape={array.shape}"
            )
        if not np.issubdtype(array.dtype, np.integer):
            raise ValueError(
                f"semantic array must use an integer dtype: {path}, dtype={array.dtype}"
            )
        return (int(array.shape[0]), int(array.shape[1])), array.dtype
    finally:
        del array


def inspect_dataset_contract(
    first_pair: FramePair,
    expected_dtype: str,
) -> DatasetContract:
    whole_shape, whole_dtype = _inspect_array(first_pair.whole_path)
    reference_shape, reference_dtype = _inspect_array(first_pair.reference_path)
    if whole_shape != reference_shape:
        raise ValueError(
            f"first frame shape mismatch: whole={whole_shape}, "
            f"reference={reference_shape}"
        )
    if whole_dtype != reference_dtype:
        raise ValueError(
            f"first frame dtype mismatch: whole={whole_dtype}, "
            f"reference={reference_dtype}"
        )
    if expected_dtype and whole_dtype != np.dtype(expected_dtype):
        raise ValueError(
            f"semantic dtype={whole_dtype}, mapping declares {expected_dtype}"
        )
    return DatasetContract(shape=whole_shape, dtype=whole_dtype)


def load_pair_arrays(
    pair: FramePair,
    contract: DatasetContract,
) -> Tuple[np.ndarray, np.ndarray]:
    whole = np.load(pair.whole_path, allow_pickle=False)
    reference = np.load(pair.reference_path, allow_pickle=False)
    for array, path, source in (
        (whole, pair.whole_path, "whole_scene"),
        (reference, pair.reference_path, "excavator_only"),
    ):
        if array.ndim != 2:
            raise ValueError(
                f"{source} semantic array must be 2D for frame "
                f"{pair.frame_id}: {path}, shape={array.shape}"
            )
        if array.shape != contract.shape:
            raise ValueError(
                f"{source} shape mismatch for frame {pair.frame_id}: "
                f"expected={contract.shape}, actual={array.shape}"
            )
        if array.dtype != contract.dtype:
            raise ValueError(
                f"{source} dtype mismatch for frame {pair.frame_id}: "
                f"expected={contract.dtype}, actual={array.dtype}"
            )
    return whole, reference

