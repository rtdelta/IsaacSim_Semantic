"""Shared semantic label normalization and dataset-ID mapping utilities."""

from __future__ import annotations

import colorsys
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = 1
BACKGROUND_ID = 0
BACKGROUND_LABEL = "BACKGROUND"
UNKNOWN_ID = 65535
UNKNOWN_LABEL = "UNLABELLED"


def canonical_label(value: Any, semantic_type: str = "class") -> str | None:
    """Return the final non-empty label from a semantic value.

    Isaac can merge inherited labels into values such as
    ``simpleroom,towelroom01wallside``. The dataset convention is to keep only
    the final label, which represents the most specific semantic assignment.
    """
    if value is None:
        return None

    if isinstance(value, Mapping):
        if semantic_type in value:
            return canonical_label(value[semantic_type], semantic_type)
        labels = [canonical_label(item, semantic_type) for item in value.values()]
        labels = [label for label in labels if label]
        return labels[-1] if labels else None

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        labels = [canonical_label(item, semantic_type) for item in value]
        labels = [label for label in labels if label]
        return labels[-1] if labels else None

    if not isinstance(value, (str, bytes, bytearray)):
        try:
            items = list(value)
        except TypeError:
            pass
        else:
            labels = [canonical_label(item, semantic_type) for item in items]
            labels = [label for label in labels if label]
            return labels[-1] if labels else None

    text = str(value).strip()
    if not text:
        return None
    labels = [item.strip() for item in text.split(",") if item.strip()]
    return labels[-1] if labels else None


def _jsonable_semantic_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable_semantic_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable_semantic_value(item) for item in value]
    try:
        return [_jsonable_semantic_value(item) for item in value]
    except TypeError:
        return str(value)


def _unique_color(label: str, occupied: set[tuple[int, int, int]]) -> list[int]:
    for salt in range(1024):
        digest = hashlib.sha256(f"{label}:{salt}".encode("utf-8")).digest()
        hue = int.from_bytes(digest[:2], "big") / 65535.0
        saturation = 0.58 + (digest[2] / 255.0) * 0.28
        value = 0.72 + (digest[3] / 255.0) * 0.25
        rgb_float = colorsys.hsv_to_rgb(hue, saturation, value)
        rgb = tuple(int(round(channel * 255)) for channel in rgb_float)
        if rgb not in occupied and rgb not in {(0, 0, 0), (255, 0, 255)}:
            occupied.add(rgb)
            return list(rgb)
    raise RuntimeError(f"Unable to allocate a unique color for label: {label}")


def build_schema_from_stage(stage: Any, source_usd: str, semantic_type: str = "class") -> dict[str, Any]:
    """Build a deterministic mapping configuration from authored USD labels."""
    attribute_name = f"semantics:labels:{semantic_type}"
    occurrences: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"source_values": [], "prim_paths": []}
    )
    semantic_prim_count = 0

    for prim in stage.Traverse():
        attribute = prim.GetAttribute(attribute_name)
        if not attribute or not attribute.IsValid() or not attribute.HasAuthoredValueOpinion():
            continue
        raw_value = attribute.Get()
        label = canonical_label(raw_value, semantic_type)
        if not label:
            continue
        semantic_prim_count += 1
        entry = occurrences[label]
        source_value = _jsonable_semantic_value(raw_value)
        if source_value not in entry["source_values"]:
            entry["source_values"].append(source_value)
        entry["prim_paths"].append(str(prim.GetPath()))

    if not occurrences:
        raise RuntimeError(
            f"No authored {attribute_name!r} attributes were found in USD: {source_usd}"
        )

    occupied = {(0, 0, 0), (255, 0, 255)}
    classes = []
    for class_id, label in enumerate(sorted(occurrences, key=lambda item: (item.casefold(), item)), start=1):
        details = occurrences[label]
        classes.append(
            {
                "id": class_id,
                "label": label,
                "color": _unique_color(label, occupied),
                "prim_count": len(details["prim_paths"]),
                "source_values": details["source_values"],
                "prim_paths": sorted(details["prim_paths"]),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_usd": str(Path(source_usd).resolve()),
        "semantic_type": semantic_type,
        "label_resolution": "last_nonempty_comma_separated_label",
        "dataset_dtype": "uint16",
        "semantic_prim_count": semantic_prim_count,
        "class_count": len(classes),
        "background": {
            "id": BACKGROUND_ID,
            "label": BACKGROUND_LABEL,
            "color": [0, 0, 0],
        },
        "unknown": {
            "id": UNKNOWN_ID,
            "label": UNKNOWN_LABEL,
            "color": [255, 0, 255],
            "policy": "error",
        },
        "classes": classes,
    }


def load_schema(schema_or_path: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(schema_or_path, Mapping):
        schema = dict(schema_or_path)
    else:
        with Path(schema_or_path).open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
    validate_schema(schema)
    return schema


def validate_schema(schema: Mapping[str, Any]) -> None:
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported semantic schema version: {schema.get('schema_version')}")
    if schema.get("dataset_dtype") != "uint16":
        raise ValueError("This writer currently requires dataset_dtype='uint16'")

    entries = [schema.get("background", {}), *schema.get("classes", []), schema.get("unknown", {})]
    ids: set[int] = set()
    labels: set[str] = set()
    colors: set[tuple[int, int, int]] = set()
    folded_labels: set[str] = set()

    for entry in entries:
        class_id = entry.get("id")
        label = entry.get("label")
        color = entry.get("color")
        if not isinstance(class_id, int) or not 0 <= class_id <= np.iinfo(np.uint16).max:
            raise ValueError(f"Invalid uint16 class ID: {class_id!r}")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Invalid class label: {label!r}")
        if class_id in ids or label in labels or label.casefold() in folded_labels:
            raise ValueError(f"Duplicate semantic ID or label: {class_id}, {label!r}")
        if not isinstance(color, list) or len(color) != 3 or any(
            not isinstance(channel, int) or not 0 <= channel <= 255 for channel in color
        ):
            raise ValueError(f"Invalid RGB color for {label!r}: {color!r}")
        rgb = tuple(color)
        if rgb in colors:
            raise ValueError(f"Duplicate RGB color: {color!r}")
        ids.add(class_id)
        labels.add(label)
        folded_labels.add(label.casefold())
        colors.add(rgb)

    if schema["background"]["id"] != BACKGROUND_ID:
        raise ValueError("Background class ID must be 0")
    if schema["unknown"].get("policy") not in {"error", "use_unknown"}:
        raise ValueError("unknown.policy must be 'error' or 'use_unknown'")


class SemanticMapping:
    """Convert Isaac runtime IDs to stable dataset IDs and custom colors."""

    _BACKGROUND_ALIASES = {"", "background", "unlabelled", "unlabeled", "none"}

    def __init__(self, schema_or_path: str | Path | Mapping[str, Any]):
        self.schema = load_schema(schema_or_path)
        self.semantic_type = self.schema["semantic_type"]
        entries = [self.schema["background"], *self.schema["classes"], self.schema["unknown"]]
        self.label_to_id = {entry["label"]: entry["id"] for entry in entries}
        self.folded_label_to_id = {entry["label"].casefold(): entry["id"] for entry in entries}
        self.id_to_label = {entry["id"]: entry["label"] for entry in entries}
        self.background_id = self.schema["background"]["id"]
        self.unknown_id = self.schema["unknown"]["id"]
        self.unknown_policy = self.schema["unknown"]["policy"]
        self.color_lut = np.zeros((np.iinfo(np.uint16).max + 1, 3), dtype=np.uint8)
        for entry in entries:
            self.color_lut[entry["id"]] = entry["color"]

    def resolve_dataset_id(self, label_info: Any) -> tuple[int, str | None]:
        label = canonical_label(label_info, self.semantic_type)
        if label is None or label.casefold() in self._BACKGROUND_ALIASES:
            return self.background_id, label
        if label in self.label_to_id:
            return self.label_to_id[label], label
        folded = label.casefold()
        if folded in self.folded_label_to_id:
            return self.folded_label_to_id[folded], label
        return self.unknown_id, label

    def remap(
        self,
        runtime_ids: np.ndarray,
        id_to_labels: Mapping[Any, Any],
        strict: bool = True,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        runtime_ids = np.asarray(runtime_ids, dtype=np.uint32)
        if runtime_ids.ndim != 2:
            raise ValueError(f"Runtime semantic IDs must be a 2D image, got {runtime_ids.shape}")

        normalized_labels = {int(key): value for key, value in id_to_labels.items()}
        dataset_ids = np.full(runtime_ids.shape, self.unknown_id, dtype=np.uint16)
        runtime_mapping: dict[str, dict[str, Any]] = {}
        unknown_labels: list[str] = []

        for runtime_id_value in np.unique(runtime_ids):
            runtime_id = int(runtime_id_value)
            label_info = normalized_labels.get(runtime_id)
            if label_info is None and runtime_id == 0:
                dataset_id, label = self.background_id, BACKGROUND_LABEL
            else:
                dataset_id, label = self.resolve_dataset_id(label_info)
            if dataset_id == self.unknown_id:
                unknown_labels.append(label if label is not None else f"<runtime-id:{runtime_id}>")
            dataset_ids[runtime_ids == runtime_id] = dataset_id
            runtime_mapping[str(runtime_id)] = {
                "source": _jsonable_semantic_value(label_info),
                "resolved_label": label,
                "dataset_id": dataset_id,
                "dataset_label": self.id_to_label[dataset_id],
            }

        should_error = strict
        if unknown_labels and should_error:
            joined = ", ".join(sorted(set(unknown_labels)))
            raise KeyError(f"Semantic labels are missing from the mapping config: {joined}")

        unique_ids, counts = np.unique(dataset_ids, return_counts=True)
        diagnostics = {
            "runtime_id_mapping": runtime_mapping,
            "dataset_pixel_counts": {
                str(int(class_id)): int(count) for class_id, count in zip(unique_ids, counts)
            },
            "unknown_labels": sorted(set(unknown_labels)),
        }
        return dataset_ids, diagnostics

    def colorize(self, dataset_ids: np.ndarray) -> np.ndarray:
        dataset_ids = np.asarray(dataset_ids)
        if dataset_ids.ndim != 2 or not np.issubdtype(dataset_ids.dtype, np.integer):
            raise ValueError("Dataset semantic IDs must be a 2D integer array")
        if dataset_ids.size and (dataset_ids.min() < 0 or dataset_ids.max() > np.iinfo(np.uint16).max):
            raise ValueError("Dataset semantic IDs exceed uint16 range")
        return self.color_lut[dataset_ids.astype(np.uint16, copy=False)]
