"""Stable semantic-label mapping used by the custom Writer and validator."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = 1
BACKGROUND_ID = 0
UNKNOWN_ID = 65535


def canonical_label(value: Any, semantic_type: str = "class") -> str | None:
    """Resolve inherited/comma-separated Isaac labels to one dataset label."""
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
    text = str(value).strip()
    labels = [item.strip() for item in text.split(",") if item.strip()]
    return labels[-1] if labels else None


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [jsonable(item) for item in value]
    try:
        return [jsonable(item) for item in value]
    except TypeError:
        return str(value)


def load_schema(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        schema = json.load(stream)
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version: {schema.get('schema_version')}")
    if schema.get("dataset_dtype") != "uint16":
        raise ValueError("dataset_dtype must be uint16")
    entries = [schema["background"], *schema["classes"], schema["unknown"]]
    ids = [entry["id"] for entry in entries]
    labels = [entry["label"].casefold() for entry in entries]
    colors = [tuple(entry["color"]) for entry in entries]
    if len(ids) != len(set(ids)) or len(labels) != len(set(labels)) or len(colors) != len(set(colors)):
        raise ValueError("Semantic IDs, labels, and colors must be unique")
    if schema["background"]["id"] != BACKGROUND_ID:
        raise ValueError("Background ID must be 0")
    return schema


class SemanticMapping:
    """Map per-run Isaac IDs to stable uint16 IDs and deterministic colors."""

    _BACKGROUND_ALIASES = {"", "background", "unlabelled", "unlabeled", "none"}

    def __init__(self, schema_path: str | Path) -> None:
        self.schema = load_schema(schema_path)
        self.semantic_type = self.schema["semantic_type"]
        entries = [self.schema["background"], *self.schema["classes"], self.schema["unknown"]]
        self.label_to_id = {entry["label"].casefold(): int(entry["id"]) for entry in entries}
        self.id_to_label = {int(entry["id"]): entry["label"] for entry in entries}
        self.background_id = int(self.schema["background"]["id"])
        self.unknown_id = int(self.schema["unknown"]["id"])
        self.color_lut = np.zeros((np.iinfo(np.uint16).max + 1, 3), dtype=np.uint8)
        for entry in entries:
            self.color_lut[int(entry["id"])] = entry["color"]

    def resolve(self, label_info: Any) -> tuple[int, str | None]:
        label = canonical_label(label_info, self.semantic_type)
        if label is None or label.casefold() in self._BACKGROUND_ALIASES:
            return self.background_id, label
        return self.label_to_id.get(label.casefold(), self.unknown_id), label

    def remap(
        self,
        runtime_ids: np.ndarray,
        id_to_labels: Mapping[Any, Any],
        strict: bool = True,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        runtime_ids = np.asarray(runtime_ids, dtype=np.uint32)
        if runtime_ids.ndim != 2:
            raise ValueError(f"Runtime semantic IDs must be 2D, got {runtime_ids.shape}")
        normalized = {int(key): value for key, value in id_to_labels.items()}
        dataset_ids = np.full(runtime_ids.shape, self.unknown_id, dtype=np.uint16)
        runtime_mapping: dict[str, Any] = {}
        unknown_labels: list[str] = []
        for raw_runtime_id in np.unique(runtime_ids):
            runtime_id = int(raw_runtime_id)
            label_info = normalized.get(runtime_id)
            if runtime_id == 0 and label_info is None:
                dataset_id, label = self.background_id, "BACKGROUND"
            else:
                dataset_id, label = self.resolve(label_info)
            if dataset_id == self.unknown_id:
                unknown_labels.append(label or f"<runtime-id:{runtime_id}>")
            dataset_ids[runtime_ids == runtime_id] = dataset_id
            runtime_mapping[str(runtime_id)] = {
                "source": jsonable(label_info),
                "resolved_label": label,
                "dataset_id": dataset_id,
                "dataset_label": self.id_to_label[dataset_id],
            }
        if unknown_labels and strict:
            raise KeyError(
                "Semantic labels are missing from the mapping: " + ", ".join(sorted(set(unknown_labels)))
            )
        ids, counts = np.unique(dataset_ids, return_counts=True)
        diagnostics = {
            "runtime_id_mapping": runtime_mapping,
            "dataset_pixel_counts": {str(int(i)): int(count) for i, count in zip(ids, counts)},
            "unknown_labels": sorted(set(unknown_labels)),
        }
        return dataset_ids, diagnostics

    def colorize(self, dataset_ids: np.ndarray) -> np.ndarray:
        values = np.asarray(dataset_ids)
        if values.ndim != 2 or not np.issubdtype(values.dtype, np.integer):
            raise ValueError("Dataset semantic IDs must be a 2D integer image")
        return self.color_lut[values.astype(np.uint16, copy=False)]
