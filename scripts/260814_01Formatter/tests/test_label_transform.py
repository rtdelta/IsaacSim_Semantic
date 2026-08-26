from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from formatter.label_transform import transform_label_file


class LabelTransformTests(unittest.TestCase):
    def test_rewrites_only_class_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            destination = root / "output" / "target.txt"
            source.write_text(
                "4 0.10000000 0.20000000 0.30000000 0.40000000\n",
                encoding="utf-8",
            )
            result = transform_label_file(
                category="tooth", source=source, destination=destination
            )
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "0 0.10000000 0.20000000 0.30000000 0.40000000\n",
            )
            self.assertEqual(result.line_count, 1)
            self.assertEqual(dict(result.original_classes), {4: 1})

    def test_empty_label_remains_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            destination = root / "target.txt"
            source.write_text("", encoding="utf-8")
            result = transform_label_file(
                category="collision", source=source, destination=destination
            )
            self.assertEqual(destination.read_text(encoding="utf-8"), "")
            self.assertTrue(result.empty)

    def test_non_finite_coordinate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("1 nan 0.2 0.3 0.4\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite coordinate"):
                transform_label_file(
                    category="tooth",
                    source=source,
                    destination=root / "target.txt",
                )

    def test_wrong_column_count_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("1 0.2 0.3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected 5"):
                transform_label_file(
                    category="tooth",
                    source=source,
                    destination=root / "target.txt",
                )


if __name__ == "__main__":
    unittest.main()
