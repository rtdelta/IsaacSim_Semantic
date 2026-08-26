from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from semantic_pixel_ratio.config import load_config
from semantic_pixel_ratio.pipeline import run
from tests.helpers import write_config, write_frames, write_mapping


class PipelineIntegrationTests(unittest.TestCase):
    def test_numpy_pipeline_writes_deterministic_reports_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            whole_directory = root / "whole"
            reference_directory = root / "reference"
            mapping = root / "mapping.json"
            config_path = root / "config.json"
            output = root / "output"

            whole_frames = [
                np.asarray([[1, 1, 2], [3, 4, 5]], dtype=np.uint16),
                np.asarray([[1, 0, 0], [0, 0, 0]], dtype=np.uint16),
                np.asarray([[5, 5, 5], [1, 2, 3]], dtype=np.uint16),
            ]
            reference_frames = [
                np.asarray([[1, 1, 2], [3, 4, 5]], dtype=np.uint16),
                np.asarray([[1, 1, 0], [0, 0, 0]], dtype=np.uint16),
                np.asarray([[5, 5, 0], [1, 2, 4]], dtype=np.uint16),
            ]
            write_frames(
                whole_directory,
                reference_directory,
                whole_frames,
                reference_frames,
            )
            write_mapping(mapping)
            write_config(
                config_path,
                whole_directory,
                reference_directory,
                mapping,
                output,
            )
            config = load_config(config_path)

            first_summary = run(config)
            second_summary = run(config)

            self.assertEqual(first_summary["frames"], 3)
            self.assertEqual(second_summary["frames"], 3)
            self.assertTrue((output / "counts_cache.npz").is_file())
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "summary.json").is_file())
            with (output / "per_frame.csv").open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 18)
            self.assertEqual(
                [row["frame_id"] for row in rows[::6]],
                ["0000", "0001", "0002"],
            )
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "completed")
            counts_manifest = json.loads(
                (output / "counts_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(counts_manifest["completed_frames"], 3)
            self.assertEqual(len(counts_manifest["parts"]), 2)


if __name__ == "__main__":
    unittest.main()

