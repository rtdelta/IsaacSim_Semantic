"""Pure-Python tests for versioned render profiles."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from render_profile import (
    RenderProfile,
    RenderProfileApplicationError,
    RenderProfileManager,
)


class FakeSettings:
    def __init__(self) -> None:
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class RejectingSettings(FakeSettings):
    def set(self, key, value):
        if key == "/rtx/rendermode":
            return
        super().set(key, value)


class RenderProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "profile.json"
        self.path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "test",
                    "renderer": "RaytracedLighting",
                    "rt_subframes": 16,
                    "settings": {"rtx/post/dlss/execMode": 2},
                    "required_settings": ["rtx/post/dlss/execMode"],
                    "metadata": {"dlss_mode": "Quality"},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loads_and_overrides_subframes(self) -> None:
        profile = RenderProfile.load(self.path)
        self.assertEqual(profile.rt_subframes, 16)
        self.assertEqual(profile.with_rt_subframes(8).rt_subframes, 8)
        self.assertEqual(len(profile.source_sha256), 64)

    def test_applies_and_reads_back_required_settings(self) -> None:
        profile = RenderProfile.load(self.path)
        settings = FakeSettings()
        snapshot = RenderProfileManager(settings).apply_and_snapshot(profile)
        self.assertEqual(snapshot["effective"]["rtx/post/dlss/execMode"], 2)
        self.assertEqual(snapshot["mismatches"], [])

    def test_rejects_undefined_required_setting(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["required_settings"].append("missing")
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not defined"):
            RenderProfile.load(self.path)

    def test_loads_both_schema_v2_renderer_profiles(self) -> None:
        config_dir = Path(__file__).resolve().parents[1] / "configs"
        realtime = RenderProfile.load(config_dir / "render_realtime_pathtracing_720p.json")
        pathtracing = RenderProfile.load(config_dir / "render_pathtracing_720p_64spp.json")

        self.assertEqual(realtime.renderer, "RealTimePathTracing")
        self.assertEqual(realtime.launch_config(True)["anti_aliasing"], 3)
        self.assertEqual(realtime.sampling_summary()["dlss_exec_mode"], 2)
        self.assertEqual(pathtracing.renderer, "PathTracing")
        self.assertEqual(pathtracing.launch_config(True)["samples_per_pixel_per_frame"], 8)
        self.assertEqual(pathtracing.sampling_summary()["planned_spp_per_output"], 64)

    def test_capture_overrides_preserve_profile_source(self) -> None:
        config = (
            Path(__file__).resolve().parents[1]
            / "configs"
            / "render_pathtracing_720p_64spp.json"
        )
        profile = RenderProfile.load(config).with_capture_overrides(
            rt_subframes=4,
            warmup_render_frames=0,
        )
        self.assertEqual(profile.rt_subframes, 4)
        self.assertEqual(profile.warmup_render_frames, 0)
        self.assertEqual(profile.sampling_summary()["nominal_spp_per_output"], 32)

    def test_pathtracing_rejects_dlss_setting(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "configs"
            / "render_pathtracing_720p_64spp.json"
        )
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["settings"]["/rtx/post/dlss/execMode"] = 2
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not define a DLSS"):
            RenderProfile.load(self.path)

    def test_realtime_rejects_pathtracing_sampling(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "configs"
            / "render_realtime_pathtracing_720p.json"
        )
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["settings"]["/rtx/pathtracing/spp"] = 8
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not define PathTracing SPP"):
            RenderProfile.load(self.path)

    def test_readback_failure_retains_manifest_snapshot(self) -> None:
        config = (
            Path(__file__).resolve().parents[1]
            / "configs"
            / "render_realtime_pathtracing_720p.json"
        )
        profile = RenderProfile.load(config)
        with self.assertRaises(RenderProfileApplicationError) as caught:
            RenderProfileManager(RejectingSettings()).apply_and_snapshot(profile)
        snapshot = caught.exception.snapshot
        self.assertEqual(snapshot["renderer"]["requested"], "RealTimePathTracing")
        self.assertIsNone(snapshot["renderer"]["effective"])
        self.assertEqual(snapshot["mismatches"][0]["key"], "/rtx/rendermode")


if __name__ == "__main__":
    unittest.main()
