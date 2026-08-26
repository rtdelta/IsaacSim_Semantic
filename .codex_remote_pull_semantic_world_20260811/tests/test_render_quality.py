"""Tests for deterministic image quality metrics."""

from __future__ import annotations

import unittest

import numpy as np

from compare_render_quality import compare, parse_roi


class RenderQualityTests(unittest.TestCase):
    def test_identical_images_have_perfect_metrics(self) -> None:
        image = np.full((8, 8, 3), 127, dtype=np.uint8)
        metrics = compare(image, image.copy())
        self.assertEqual(metrics["rmse"], 0.0)
        self.assertEqual(metrics["global_ssim"], 1.0)
        self.assertIsNone(metrics["psnr_db"])
        self.assertTrue(metrics["identical"])

    def test_roi_is_bounds_checked(self) -> None:
        self.assertEqual(parse_roi("1,2,3,4", 10, 10), (1, 2, 3, 4))
        with self.assertRaisesRegex(ValueError, "bounds"):
            parse_roi("8,8,3,3", 10, 10)


if __name__ == "__main__":
    unittest.main()
