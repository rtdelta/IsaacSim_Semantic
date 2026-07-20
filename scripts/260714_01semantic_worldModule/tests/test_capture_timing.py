"""Tests for fixed-step capture frame timing."""

from __future__ import annotations

import unittest

from capture_timing import CaptureTiming


class CaptureTimingTests(unittest.TestCase):
    def test_initial_frame_starts_at_zero(self) -> None:
        timing = CaptureTiming(physics_hz=60, capture_fps=10, capture_initial_frame=True)
        self.assertEqual(timing.steps_per_capture, 6)
        self.assertEqual(timing.data_step_for_frame(0), 0)
        self.assertAlmostEqual(timing.dataset_time_for_frame(2), 0.2)

    def test_legacy_first_frame_starts_after_one_interval(self) -> None:
        timing = CaptureTiming(physics_hz=60, capture_fps=10, capture_initial_frame=False)
        self.assertEqual(timing.data_step_for_frame(0), 6)
        self.assertAlmostEqual(timing.dataset_time_for_frame(2), 0.3)

    def test_static_capture_does_not_advance_data_time(self) -> None:
        timing = CaptureTiming(physics_hz=60, capture_fps=10, static=True)
        self.assertEqual(timing.data_step_for_frame(100), 0)
        self.assertEqual(timing.dataset_time_for_frame(100), 0.0)

    def test_rejects_non_integral_schedule(self) -> None:
        with self.assertRaisesRegex(ValueError, "divisible"):
            CaptureTiming(physics_hz=60, capture_fps=11)


if __name__ == "__main__":
    unittest.main()
