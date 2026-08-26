from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from semantic_pixel_ratio.discovery import discover_frame_pairs


class DiscoveryTests(unittest.TestCase):
    def test_numeric_frame_ids_are_sorted_numerically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            whole = root / "whole"
            reference = root / "reference"
            whole.mkdir()
            reference.mkdir()
            for frame_id in ("10", "2", "1"):
                array = np.zeros((2, 2), dtype=np.uint16)
                np.save(whole / f"semantic_id_{frame_id}.npy", array)
                np.save(reference / f"semantic_id_{frame_id}.npy", array)

            pairs = discover_frame_pairs(whole, reference)

            self.assertEqual([item.frame_id for item in pairs], ["1", "2", "10"])
            self.assertEqual([item.ordinal for item in pairs], [0, 1, 2])

    def test_mismatched_frame_sets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            whole = root / "whole"
            reference = root / "reference"
            whole.mkdir()
            reference.mkdir()
            np.save(
                whole / "semantic_id_0000.npy",
                np.zeros((2, 2), dtype=np.uint16),
            )
            np.save(
                reference / "semantic_id_0001.npy",
                np.zeros((2, 2), dtype=np.uint16),
            )

            with self.assertRaisesRegex(ValueError, "frame sets do not match"):
                discover_frame_pairs(whole, reference)


if __name__ == "__main__":
    unittest.main()

