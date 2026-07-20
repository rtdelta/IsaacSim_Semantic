"""Pure tests for preflight issue handling and file records."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stage_preflight import PreflightReport, file_record


class StagePreflightSupportTests(unittest.TestCase):
    def test_file_record_hashes_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "asset.usda"
            path.write_text("#usda 1.0\n", encoding="utf-8")
            record = file_record(path)
        self.assertTrue(record["exists"])
        self.assertEqual(len(record["sha256"]), 64)

    def test_strict_report_raises_only_for_errors(self) -> None:
        report = PreflightReport()
        report.add("warning", "WARN", "warning")
        report.raise_if_blocking(strict=True)
        report.add("error", "BROKEN", "broken", "/root/Prim")
        with self.assertRaisesRegex(RuntimeError, "BROKEN"):
            report.raise_if_blocking(strict=True)
        report.raise_if_blocking(strict=False)

    def test_unusable_stage_errors_always_raise(self) -> None:
        report = PreflightReport()
        report.add("error", "ASSET_UNRESOLVED", "missing optional diagnostic asset")
        report.raise_if_unusable()
        report.add("error", "CAMERA_INVALID", "missing camera")
        with self.assertRaisesRegex(RuntimeError, "not usable"):
            report.raise_if_unusable()


if __name__ == "__main__":
    unittest.main()
