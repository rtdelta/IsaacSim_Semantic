from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from threshold_filter.config import load_config
from threshold_filter.pipeline import run_pipeline
from tests.helpers import create_dataset


def label_contents(root: Path) -> dict:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted((root / "modules").rglob("*.txt"))
    }


class DeterminismTests(unittest.TestCase):
    def test_worker_count_does_not_change_labels_and_source_stays_unchanged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            one_config, one_output, _ = create_dataset(
                root / "one",
                output_name="output",
                workers=1,
            )
            four_config, four_output, _ = create_dataset(
                root / "four",
                output_name="output",
                workers=4,
            )
            source_label = (
                root
                / "one"
                / "post"
                / "modules"
                / "tooth_boxes"
                / "rgb_0001.txt"
            )
            source_before = source_label.read_bytes()

            run_pipeline(load_config(one_config))
            run_pipeline(load_config(four_config))

            self.assertEqual(label_contents(one_output), label_contents(four_output))
            self.assertEqual(source_label.read_bytes(), source_before)
            output_label = (
                one_output / "modules" / "tooth_boxes" / "rgb_0001.txt"
            )
            output_label.write_text("changed\n", encoding="utf-8")
            self.assertEqual(source_label.read_bytes(), source_before)


if __name__ == "__main__":
    unittest.main()
