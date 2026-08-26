"""Configurable semantic-ID normalization shared by camera annotators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError


@dataclass(frozen=True)
class SemanticClass:
    class_id: int
    name: str
    color: tuple[int, int, int]


class SemanticMapping:
    """Map raw annotator labels/IDs to stable dataset class IDs."""

    def __init__(self, classes: tuple[SemanticClass, ...], aliases: dict[str, int]) -> None:
        self.classes = classes
        # Isaac/Replicator versions do not preserve semantic-label casing
        # consistently (for example ``3DGS`` may be reported as ``3dgs``).
        # USD labels are identifiers here, so match them case-insensitively.
        self.aliases = {str(name).casefold(): class_id for name, class_id in aliases.items()}
        self.by_id = {item.class_id: item for item in classes}

    @classmethod
    def load(cls, path: str | Path) -> "SemanticMapping":
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Semantic mapping does not exist: {source}") from exc
        entries = raw.get("classes") if isinstance(raw, dict) else raw
        if not isinstance(entries, list) or not entries:
            raise ConfigurationError("Semantic mapping must contain a non-empty classes list")
        classes: list[SemanticClass] = []
        aliases: dict[str, int] = {}
        for index, value in enumerate(entries):
            if not isinstance(value, dict):
                raise ConfigurationError(f"Semantic class {index} must be an object")
            class_id = value.get("id")
            name = value.get("name", value.get("label"))
            color = value.get("color", [0, 0, 0])
            if isinstance(class_id, bool) or not isinstance(class_id, int) or class_id < 0:
                raise ConfigurationError(f"Semantic class {index}.id must be non-negative")
            if not isinstance(name, str) or not name:
                raise ConfigurationError(f"Semantic class {index}.name must be a string")
            if not isinstance(color, list) or len(color) != 3 or any(
                isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255
                for item in color
            ):
                raise ConfigurationError(f"Semantic class {index}.color must be [r,g,b]")
            item = SemanticClass(class_id, name, tuple(color))
            classes.append(item)
            for alias in [name, *value.get("aliases", [])]:
                aliases[str(alias)] = class_id
        if len({item.class_id for item in classes}) != len(classes):
            raise ConfigurationError("Semantic mapping contains duplicate class IDs")
        return cls(tuple(classes), aliases)

    def raw_id_lookup(self, annotator_info: Any) -> dict[int, int]:
        """Resolve Replicator idToLabels shapes without coupling the core to one version."""

        if not isinstance(annotator_info, dict):
            return {}
        candidates = annotator_info.get("idToLabels", annotator_info.get("id_to_labels", {}))
        if not isinstance(candidates, dict):
            return {}
        lookup: dict[int, int] = {}
        for raw_id, label_value in candidates.items():
            label = label_value
            if isinstance(label_value, dict):
                label = next(
                    (label_value[key] for key in ("class", "label", "name") if key in label_value),
                    "",
                )
            normalized = str(label)
            if "," in normalized:
                normalized = next(
                    (item.strip() for item in reversed(normalized.split(",")) if item.strip()),
                    normalized,
                )
            target = self.aliases.get(normalized.casefold())
            if target is not None:
                try:
                    lookup[int(raw_id)] = target
                except (TypeError, ValueError):
                    continue
        return lookup

    def remap(self, raw_ids: Any, annotator_info: Any, *, unknown_id: int = 0) -> Any:
        import numpy as np

        source = np.asarray(raw_ids)
        if source.ndim >= 3 and source.shape[-1] == 1:
            source = source[..., 0]
        maximum_id = max([unknown_id, *self.by_id], default=unknown_id)
        if maximum_id <= np.iinfo(np.uint16).max:
            dtype = np.uint16
        elif maximum_id <= np.iinfo(np.uint32).max:
            dtype = np.uint32
        else:
            dtype = np.uint64
        result = np.full(source.shape, unknown_id, dtype=dtype)
        for raw_id, class_id in self.raw_id_lookup(annotator_info).items():
            result[source == raw_id] = class_id
        return result

    def colorize(self, class_ids: Any) -> Any:
        import numpy as np

        source = np.asarray(class_ids)
        image = np.zeros((*source.shape, 3), dtype=np.uint8)
        for class_id, item in self.by_id.items():
            image[source == class_id] = item.color
        return image
