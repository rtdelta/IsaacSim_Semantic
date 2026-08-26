from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from formatter.materializer import materialize_file
from formatter.models import MaterializeOperation


class MaterializerTests(unittest.TestCase):
    def test_hardlink_or_copy_prefers_hardlink_on_same_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            destination = root / "output" / "renamed.png"
            source.write_bytes(b"image")
            result = materialize_file(
                MaterializeOperation("image", source, destination),
                "hardlink_or_copy",
            )
            self.assertEqual(result.mode, "hardlink")
            source_stat = source.stat()
            destination_stat = destination.stat()
            self.assertEqual(
                (source_stat.st_dev, source_stat.st_ino),
                (destination_stat.st_dev, destination_stat.st_ino),
            )

    def test_copy_mode_creates_independent_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            destination = root / "output" / "target.txt"
            source.write_text("value", encoding="utf-8")
            result = materialize_file(
                MaterializeOperation("report", source, destination), "copy"
            )
            self.assertEqual(result.mode, "copy")
            self.assertEqual(destination.read_text(encoding="utf-8"), "value")
            if os.name != "nt":
                self.assertNotEqual(source.stat().st_ino, destination.stat().st_ino)


if __name__ == "__main__":
    unittest.main()
