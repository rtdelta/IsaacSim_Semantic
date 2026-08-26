from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, Iterable, Iterator, TypeVar


T = TypeVar("T")
R = TypeVar("R")


def bounded_parallel_map(
    function: Callable[[T], R],
    items: Iterable[T],
    *,
    workers: int,
    max_in_flight: int,
    thread_name_prefix: str,
) -> Iterator[R]:
    iterator = iter(items)
    pending: dict[Future[R], T] = {}
    exhausted = False
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix=thread_name_prefix
    ) as pool:
        try:
            while pending or not exhausted:
                while not exhausted and len(pending) < max_in_flight:
                    try:
                        item = next(iterator)
                    except StopIteration:
                        exhausted = True
                        break
                    pending[pool.submit(function, item)] = item
                if not pending:
                    continue
                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    yield future.result()
        except BaseException:
            for future in pending:
                future.cancel()
            raise
