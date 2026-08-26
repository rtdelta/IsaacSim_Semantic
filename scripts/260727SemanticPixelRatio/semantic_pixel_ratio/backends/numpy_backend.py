from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Tuple

import numpy as np

from ..models import BatchCounts, LoadedBatch
from .base import PixelCounterBackend


def _count_frame(frame_data: np.ndarray, target_ids: np.ndarray) -> np.ndarray:
    output = np.empty((2, 5), dtype=np.uint32)
    for source_index in range(2):
        histogram = np.bincount(frame_data[source_index].reshape(-1))
        for target_index, semantic_id in enumerate(target_ids):
            output[source_index, target_index] = (
                histogram[int(semantic_id)]
                if int(semantic_id) < histogram.size
                else 0
            )
    return output


class NumpyBackend(PixelCounterBackend):
    name = "numpy"

    def __init__(self, target_ids: Tuple[int, ...], workers: int) -> None:
        super().__init__(target_ids)
        self._target_ids = np.asarray(target_ids, dtype=np.int64)
        self._pool = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="semantic-numpy-counter",
        )

    def count_batch(self, batch: LoadedBatch) -> BatchCounts:
        futures = [
            self._pool.submit(_count_frame, batch.data[index], self._target_ids)
            for index in range(len(batch.pairs))
        ]
        counts = np.stack([future.result() for future in futures], axis=0)
        return BatchCounts(pairs=batch.pairs, counts=counts)

    def close(self) -> None:
        self._pool.shutdown(wait=True)

