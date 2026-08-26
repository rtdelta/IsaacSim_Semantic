from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from ...common.pixel_box import PixelBox


@dataclass(frozen=True)
class TargetGeometry:
    pixel_count: int
    box: PixelBox | None
    coordinates: np.ndarray
    raw_pixel_count: int = 0
    kept_component_count: int = 0
    removed_component_count: int = 0
    removed_pixel_count: int = 0


@dataclass(frozen=True)
class SceneFeatures:
    targets: Tuple[TargetGeometry, ...]

    @property
    def counts(self) -> np.ndarray:
        return np.asarray(
            [target.pixel_count for target in self.targets], dtype=np.uint64
        )

    @property
    def raw_counts(self) -> np.ndarray:
        return np.asarray(
            [target.raw_pixel_count for target in self.targets], dtype=np.uint64
        )

    @property
    def kept_component_counts(self) -> np.ndarray:
        return np.asarray(
            [target.kept_component_count for target in self.targets], dtype=np.int32
        )

    @property
    def removed_component_counts(self) -> np.ndarray:
        return np.asarray(
            [target.removed_component_count for target in self.targets], dtype=np.int32
        )

    @property
    def removed_pixel_counts(self) -> np.ndarray:
        return np.asarray(
            [target.removed_pixel_count for target in self.targets], dtype=np.uint64
        )
