from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Tuple

from ..models import BatchCounts, LoadedBatch


class PixelCounterBackend(ABC):
    name: ClassVar[str]

    def __init__(self, target_ids: Tuple[int, ...]) -> None:
        if len(target_ids) != 5:
            raise ValueError("pixel counter requires exactly five target IDs")
        self.target_ids = target_ids

    @abstractmethod
    def count_batch(self, batch: LoadedBatch) -> BatchCounts:
        raise NotImplementedError

    def close(self) -> None:
        return None

    def __enter__(self) -> "PixelCounterBackend":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

