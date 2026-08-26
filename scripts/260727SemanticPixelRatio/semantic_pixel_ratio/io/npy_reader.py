from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterator, Sequence, Tuple, Union

import numpy as np

from ..models import DatasetContract, FramePair, LoadedBatch
from ..semantic_io import load_pair_arrays


@dataclass(frozen=True)
class _ReaderFailure:
    error: BaseException


class _ReaderEnd:
    pass


_QueueItem = Union[LoadedBatch, _ReaderFailure, _ReaderEnd]


def _chunks(
    pairs: Sequence[FramePair],
    size: int,
) -> Iterator[Tuple[FramePair, ...]]:
    for start in range(0, len(pairs), size):
        yield tuple(pairs[start : start + size])


class PrefetchingNpyReader:
    """Bounded producer that overlaps NPY loading with backend computation."""

    def __init__(
        self,
        pairs: Sequence[FramePair],
        contract: DatasetContract,
        batch_frames: int,
        reader_threads: int,
        ring_slots: int,
    ) -> None:
        self._pairs = tuple(pairs)
        self._contract = contract
        self._batch_frames = batch_frames
        self._reader_threads = reader_threads
        self._queue: "queue.Queue[_QueueItem]" = queue.Queue(maxsize=ring_slots)
        self._stop = threading.Event()
        self._producer: threading.Thread | None = None

    def _put(self, item: _QueueItem) -> bool:
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def _load_batch(
        self,
        batch_pairs: Tuple[FramePair, ...],
        pool: ThreadPoolExecutor,
    ) -> LoadedBatch:
        futures = [
            pool.submit(load_pair_arrays, pair, self._contract)
            for pair in batch_pairs
        ]
        data = np.empty(
            (
                len(batch_pairs),
                2,
                self._contract.height,
                self._contract.width,
            ),
            dtype=self._contract.dtype,
        )
        for index, future in enumerate(futures):
            whole, reference = future.result()
            np.copyto(data[index, 0], whole, casting="no")
            np.copyto(data[index, 1], reference, casting="no")
        return LoadedBatch(pairs=batch_pairs, data=data)

    def _produce(self) -> None:
        try:
            with ThreadPoolExecutor(
                max_workers=self._reader_threads,
                thread_name_prefix="semantic-npy-reader",
            ) as pool:
                for batch_pairs in _chunks(self._pairs, self._batch_frames):
                    if self._stop.is_set():
                        return
                    batch = self._load_batch(batch_pairs, pool)
                    if not self._put(batch):
                        return
            self._put(_ReaderEnd())
        except BaseException as exc:
            self._put(_ReaderFailure(exc))

    def __iter__(self) -> Iterator[LoadedBatch]:
        if self._producer is not None:
            raise RuntimeError("prefetch reader can only be iterated once")
        self._producer = threading.Thread(
            target=self._produce,
            name="semantic-batch-producer",
            daemon=True,
        )
        self._producer.start()
        try:
            while True:
                item = self._queue.get()
                if isinstance(item, _ReaderEnd):
                    return
                if isinstance(item, _ReaderFailure):
                    raise item.error
                yield item
        finally:
            self._stop.set()
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._producer.join(timeout=10)

