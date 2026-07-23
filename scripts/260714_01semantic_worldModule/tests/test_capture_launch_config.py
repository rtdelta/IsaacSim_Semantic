"""Tests for strict business-configuration loading."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from capture_launch_config import CaptureLaunchConfig


def valid_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "usd": "stage.usda",
        "mapping": "mapping.json",
        "camera_prim_path": "/World/Camera",
        "renderer": "RealTimePathTracing",
        "render_profile": "render.json",
        "warmup_render_frames": None,
        "rt_subframes": None,
        "output": "../output/run",
        "overwrite": False,
        "frames": 50,
        "width": 1280,
        "height": 720,
        "physics_hz": 60,
        "capture_fps": 10,
        "capture_mode": "motion",
        "capture_initial_frame": True,
        "pre_roll_steps": 0,
        "enable_motion": True,
        "trajectory": "../trajectories/motion.csv",
        "trajectory_mode": "hold",
        "interpolation": "linear",
        "joint_profile": "joints.json",
        "articulation_ready_timeout_steps": 240,
        "headless": True,
        "save_runtime_ids": True,
        "strict_mapping": True,
        "strict_stage": True,
    }


class CaptureLaunchConfigTests(unittest.TestCase):
    def write_config(self, directory: Path, payload: Any) -> Path:
        config_dir = directory / "configs"
        config_dir.mkdir()
        path = config_dir / "capture.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_all_fields_and_resolves_paths_from_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.write_config(root, valid_payload())
            config = CaptureLaunchConfig.load(path)

            self.assertEqual(config.source_path, path.resolve())
            self.assertEqual(config.usd, str((path.parent / "stage.usda").resolve()))
            self.assertEqual(config.output, str((root / "output" / "run").resolve()))
            self.assertEqual(
                config.trajectory,
                str((root / "trajectories" / "motion.csv").resolve()),
            )
            self.assertEqual(config.camera_prim_path, "/World/Camera")
            self.assertIsNone(config.warmup_render_frames)
            self.assertNotIn("source_path", config.to_dict())

    def test_capture_mode_and_enable_motion_remain_independent(self) -> None:
        combinations = (
            ("motion", False),
            ("static", True),
        )
        for capture_mode, enable_motion in combinations:
            with self.subTest(capture_mode=capture_mode, enable_motion=enable_motion):
                with tempfile.TemporaryDirectory() as temporary:
                    payload = valid_payload()
                    payload["capture_mode"] = capture_mode
                    payload["enable_motion"] = enable_motion
                    config = CaptureLaunchConfig.load(
                        self.write_config(Path(temporary), payload)
                    )
                    self.assertEqual(config.capture_mode, capture_mode)
                    self.assertEqual(config.enable_motion, enable_motion)

    def test_rejects_unknown_field_with_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["camera-prim-path"] = payload.pop("camera_prim_path")
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "camera_prim_path"):
                CaptureLaunchConfig.load(path)

    def test_rejects_missing_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload.pop("frames")
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "Missing.*frames"):
                CaptureLaunchConfig.load(path)

    def test_rejects_boolean_used_as_integer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["frames"] = True
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "frames"):
                CaptureLaunchConfig.load(path)

    def test_rejects_non_absolute_camera_prim_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["camera_prim_path"] = "World/Camera"
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "absolute USD Prim path"):
                CaptureLaunchConfig.load(path)

    def test_rejects_unsupported_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["schema_version"] = 2
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "Unsupported.*schema version"):
                CaptureLaunchConfig.load(path)

    def test_project_sample_is_loadable(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "configs" / "capture_motion_camera02.json"
        config = CaptureLaunchConfig.load(sample)
        self.assertEqual(
            config.camera_prim_path,
            "/root/Xform/operator_cab_mesh/Camera_02",
        )
        self.assertTrue(Path(config.usd).is_absolute())


if __name__ == "__main__":
    unittest.main()
