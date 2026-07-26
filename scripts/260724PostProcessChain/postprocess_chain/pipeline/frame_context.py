from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from ..common.models import FrameTask
from ..common.semantic_io import load_frame_resources


@dataclass(frozen=True)
class FrameContext:
    task: FrameTask
    semantic: np.ndarray
    image_width: int
    image_height: int

    @classmethod
    def load(cls, task: FrameTask, expected_dtype: str) -> "FrameContext":
        semantic, image_width, image_height = load_frame_resources(
            task,
            expected_dtype,
        )
        return cls(
            task=task,
            semantic=semantic,
            image_width=image_width,
            image_height=image_height,
        )


class FrameArtifactStore:
    def __init__(self) -> None:
        self._items: Dict[str, object] = {}

    def publish(self, module_id: str, values: Dict[str, object]) -> None:
        for name, value in values.items():
            if not name or "." in name:
                raise ValueError(
                    f"artifact name must be non-empty and local to its module: {name!r}"
                )
            reference = f"{module_id}.{name}"
            if reference in self._items:
                raise ValueError(f"artifact already exists: {reference}")
            self._items[reference] = value

    def get(self, reference: str) -> object:
        try:
            return self._items[reference]
        except KeyError as exc:
            raise KeyError(f"required frame artifact is unavailable: {reference}") from exc

    def contains(self, reference: str) -> bool:
        return reference in self._items
