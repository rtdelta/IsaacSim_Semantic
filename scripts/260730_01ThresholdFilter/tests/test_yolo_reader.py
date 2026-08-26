from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from threshold_filter.yolo_reader import parse_yolo_file


class YoloReaderTests(unittest.TestCase):
    def test_empty_file_is_a_valid_empty_annotation_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.txt"
            path.write_text("", encoding="utf-8")
            self.assertEqual(parse_yolo_file(path), ())

    def test_preserves_original_line_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "label.txt"
            source = "1 0.50000000 0.40000000 0.10000000 0.20000000"
            path.write_text(source + "\n", encoding="utf-8")
            result = parse_yolo_file(path)
            self.assertEqual(result[0].raw_line, source)

    def test_rejects_invalid_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.txt"
            path.write_text("0 1.2 0.5 0.1 0.1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside"):
                parse_yolo_file(path)


if __name__ == "__main__":
    unittest.main()
