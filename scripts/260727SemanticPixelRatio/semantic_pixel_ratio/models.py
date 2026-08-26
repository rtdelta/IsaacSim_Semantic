from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class FramePair:
    ordinal: int
    frame_id: str
    whole_path: Path
    reference_path: Path


@dataclass(frozen=True)
class DatasetContract:
    shape: Tuple[int, int]
    dtype: np.dtype

    @property
    def height(self) -> int:
        return self.shape[0]

    @property
    def width(self) -> int:
        return self.shape[1]

    @property
    def pixels_per_frame(self) -> int:
        return self.height * self.width


@dataclass(frozen=True)
class LoadedBatch:
    pairs: Tuple[FramePair, ...]
    data: np.ndarray

    def __post_init__(self) -> None:
        if self.data.ndim != 4 or self.data.shape[1] != 2:
            raise ValueError(
                "loaded batch data must have shape [batch, 2, height, width]"
            )
        if self.data.shape[0] != len(self.pairs):
            raise ValueError("loaded batch pair count does not match array batch size")


@dataclass(frozen=True)
class BatchCounts:
    pairs: Tuple[FramePair, ...]
    counts: np.ndarray

    def __post_init__(self) -> None:
        expected = (len(self.pairs), 2, 5)
        if self.counts.shape != expected:
            raise ValueError(
                f"batch counts must have shape {expected}, got {self.counts.shape}"
            )
        if not np.issubdtype(self.counts.dtype, np.integer):
            raise ValueError("batch counts must use an integer dtype")


@dataclass(frozen=True)
class CountLedgerData:
    ordinals: np.ndarray
    frame_ids: Tuple[str, ...]
    whole_counts: np.ndarray
    reference_counts: np.ndarray

    def __post_init__(self) -> None:
        size = len(self.frame_ids)
        if self.ordinals.shape != (size,):
            raise ValueError("ledger ordinals shape does not match frame IDs")
        if self.whole_counts.shape != (size, 5):
            raise ValueError("whole counts must have shape [frames, 5]")
        if self.reference_counts.shape != (size, 5):
            raise ValueError("reference counts must have shape [frames, 5]")


@dataclass(frozen=True)
class SemanticMapping:
    label_to_id: Mapping[str, int]
    expected_dtype: str


@dataclass(frozen=True)
class TargetRow:
    frame_id: str
    target: str
    whole_pixels: int
    reference_pixels: int
    ratio: Optional[float]
    status: str

