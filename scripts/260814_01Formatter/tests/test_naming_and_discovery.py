from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from formatter.discovery import discover_dataset
from formatter.naming import build_frame_plans
from tests.helpers import make_source


class NamingAndDiscoveryTests(unittest.TestCase):
    def test_padding_uses_maximum_numeric_frame_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0", "0001", "9999", "10000"])
            contract = discover_dataset(source)
            plans = build_frame_plans(contract, "PREFIX")
            self.assertEqual(contract.max_frame_id, 10000)
            self.assertEqual(contract.padding_width, 5)
            self.assertEqual(
                [plan.rgb_name for plan in plans],
                [
                    "PREFIX_00000.png",
                    "PREFIX_00001.png",
                    "PREFIX_09999.png",
                    "PREFIX_10000.png",
                ],
            )

    def test_numeric_duplicate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["1"])
            rgb = source / "dataset" / "rgb"
            (rgb / "other_0001.png").write_bytes(b"duplicate")
            with self.assertRaisesRegex(ValueError, "duplicate numeric frame ID 1"):
                discover_dataset(source)

    def test_mismatched_frame_sets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0", "1"])
            (source / "dataset" / "tooth_boxes" / "rgb_1.txt").unlink()
            with self.assertRaisesRegex(ValueError, "frame sets do not match"):
                discover_dataset(source)

    def test_unknown_dataset_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0"])
            (source / "dataset" / "unexpected.json").write_text(
                "{}", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unexpected entries"):
                discover_dataset(source)


if __name__ == "__main__":
    unittest.main()
