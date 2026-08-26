from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple

import numpy as np


@dataclass(frozen=True)
class SemanticMapping:
    label_to_id: Mapping[str, int]
    expected_dtype: str


def load_semantic_mapping(path: Path) -> SemanticMapping:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read semantic mapping {path}: {exc}") from exc
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
        if (
            isinstance(semantic_id, bool)
            or not isinstance(semantic_id, int)
            or semantic_id < 0
        ):
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
    return SemanticMapping(label_to_id=label_to_id, expected_dtype=expected_dtype)


def resolve_target_ids(
    mapping: SemanticMapping,
    labels: Tuple[str, ...],
) -> Tuple[int, ...]:
    missing = [label for label in labels if label not in mapping.label_to_id]
    if missing:
        raise ValueError(
            "semantic mapping is missing target labels: " + ", ".join(missing)
        )
    values = tuple(mapping.label_to_id[label] for label in labels)
    if len(set(values)) != len(values):
        raise ValueError("target labels must resolve to distinct semantic IDs")
    return values


def mapping_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
