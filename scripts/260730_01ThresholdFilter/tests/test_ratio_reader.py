from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from threshold_filter.config import load_config
from threshold_filter.preflight import run_preflight
from threshold_filter.ratio_reader import load_ratio_matrix
from tests.helpers import create_dataset


class RatioReaderTests(unittest.TestCase):
    def test_npz_and_csv_backends_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            npz_path, _, _ = create_dataset(
                root / "npz_dataset",
                ratio_input_format="counts_cache_npz",
                output_name="npz_output",
            )
            csv_path, _, _ = create_dataset(
                root / "csv_dataset",
                ratio_input_format="per_frame_csv",
                output_name="csv_output",
            )
            npz_config = load_config(npz_path)
            csv_config = load_config(csv_path)
            npz = load_ratio_matrix(npz_config, run_preflight(npz_config))
            csv = load_ratio_matrix(csv_config, run_preflight(csv_config))
            self.assertEqual(npz.frame_ids, csv.frame_ids)
            self.assertEqual(npz.labels, csv.labels)
            np.testing.assert_array_equal(npz.whole_counts, csv.whole_counts)
            np.testing.assert_array_equal(
                npz.reference_counts,
                csv.reference_counts,
            )
            np.testing.assert_allclose(npz.ratios, csv.ratios)


if __name__ == "__main__":
    unittest.main()
