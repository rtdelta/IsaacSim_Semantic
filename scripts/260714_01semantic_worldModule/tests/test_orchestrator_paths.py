"""Tests for the single-config command-line boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

from capture_launch_config import CaptureLaunchConfig
from capture_timing import CaptureTiming
from joint_control_profile import JointControlProfile
from render_profile import RenderProfile
from simulation_orchestrator import (
    RUN_CONFIG_SCHEMA_VERSION,
    base_manifest,
    parse_args,
    resolve_renderer_selection,
)


class OrchestratorPathTests(unittest.TestCase):
    def test_config_is_the_only_business_option(self) -> None:
        args = parse_args(["--config", "configs/capture.json"])
        self.assertEqual(args.config, "configs/capture.json")
        self.assertEqual(vars(args), {"config": "configs/capture.json"})

    def test_config_is_required(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args([])

    def test_legacy_business_option_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--config",
                    "configs/capture.json",
                    "--camera_prim_path",
                    "/root/Camera",
                ]
            )

    def test_unknown_kit_option_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--config", "configs/capture.json", "--/app/window/width=1280"])

    def test_explicit_renderer_must_match_profile(self) -> None:
        profile = RenderProfile.load(
            "configs/render_pathtracing_720p_64spp.json"
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            resolve_renderer_selection("RealTimePathTracing", profile)

    def test_manifest_records_source_and_effective_configuration(self) -> None:
        config = CaptureLaunchConfig.load("configs/capture_motion_camera02.json")
        profile = RenderProfile.load(config.render_profile).with_capture_overrides(
            rt_subframes=config.rt_subframes,
            warmup_render_frames=config.warmup_render_frames,
        )
        joint_profile = JointControlProfile.load(config.joint_profile)
        timing = CaptureTiming(
            physics_hz=config.physics_hz,
            capture_fps=config.capture_fps,
            capture_initial_frame=config.capture_initial_frame,
            static=config.capture_mode == "static",
        )

        manifest = base_manifest(
            config,
            profile,
            joint_profile,
            trajectory_metadata=None,
            timing=timing,
            output_path=Path(config.output),
            original_argv=["simulation_orchestrator.py", "--config", str(config.source_path)],
        )

        self.assertEqual(manifest["schema_version"], RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(
            manifest["launch_config"]["source"]["path"],
            str(config.source_path),
        )
        self.assertEqual(
            manifest["effective_config"]["camera_prim_path"],
            config.camera_prim_path,
        )
        self.assertEqual(
            manifest["effective_config"]["rt_subframes"],
            profile.rt_subframes,
        )


if __name__ == "__main__":
    unittest.main()
