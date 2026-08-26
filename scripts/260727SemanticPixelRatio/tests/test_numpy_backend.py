from __future__ import annotations

import unittest

import numpy as np

from semantic_pixel_ratio.backends.numpy_backend import NumpyBackend
from semantic_pixel_ratio.models import FramePair, LoadedBatch


class NumpyBackendTests(unittest.TestCase):
    def test_counts_all_five_ids_for_both_sources(self) -> None:
        data = np.asarray(
            [
                [
                    [[1, 1, 2], [3, 4, 5]],
                    [[1, 2, 2], [2, 5, 0]],
                ]
            ],
            dtype=np.uint16,
        )
        pair = FramePair(
            ordinal=0,
            frame_id="0000",
            whole_path=None,  # type: ignore[arg-type]
            reference_path=None,  # type: ignore[arg-type]
        )
        batch = LoadedBatch(pairs=(pair,), data=data)

        with NumpyBackend((1, 2, 3, 4, 5), workers=1) as backend:
            result = backend.count_batch(batch)

        np.testing.assert_array_equal(
            result.counts,
            np.asarray([[[2, 1, 1, 1, 1], [1, 3, 0, 0, 1]]]),
        )


if __name__ == "__main__":
    unittest.main()

