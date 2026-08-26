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
        "schema_version": 4,
        "usd": "stage.usda",
        "mapping": "mapping.json",
        "camera_prim_path": "/World/Camera",
        "renderer": "RealTimePathTracing",
        "render_profile": "render.json",
        "warmup_render_frames": None,
        "rt_subframes": None,
        "output": "../output/run",
        "image_output_folders": {
            "full_scene_rgb": "full_scene_excavator_rgb",
            "full_scene_semantic": "full_scene_excavator_semantic",
            "excavator_only_rgb": "excavator_only_rgb",
            "excavator_only_semantic": "excavator_only_semantic",
            "front_teeth_only_rgb": "front_teeth_only_rgb",
            "front_teeth_only_semantic": "front_teeth_only_semantic",
        },
        "excavator_only_capture": {
            "enabled": False,
            "render_prim_paths_config": None,
        },
        "front_teeth_only_capture": {
            "enabled": False,
            "render_prim_paths_config": None,
            "save_rgb": False,
        },
        "variant_transition": {
            "settle_render_count": 1,
            "settle_rt_subframes": 16,
            "maximum_settle_attempts": 3,
            "restore_full_scene_after_each_frame": True,
        },
        "variant_validation": {
            "enabled": True,
            "full_scene": {
                "allowed_labels": None,
                "required_any_labels": ["arm"],
                "forbidden_labels": [],
                "allow_empty_target": False,
            },
            "excavator_only": {
                "allowed_labels": ["arm", "tooth"],
                "required_any_labels": ["arm", "tooth"],
                "forbidden_labels": [],
                "allow_empty_target": False,
            },
            "front_teeth_only": {
                "allowed_labels": ["tooth"],
                "required_any_labels": ["tooth"],
                "forbidden_labels": ["arm"],
                "allow_empty_target": True,
            },
        },
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
        "save_runtime_ids": False,
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
            self.assertEqual(
                config.image_output_folders.full_scene_rgb,
                "full_scene_excavator_rgb",
            )
            self.assertFalse(config.excavator_only_capture.enabled)
            self.assertFalse(config.front_teeth_only_capture.enabled)
            self.assertEqual(config.variant_transition.settle_render_count, 1)
            self.assertEqual(config.variant_transition.settle_rt_subframes, 16)
            self.assertTrue(config.variant_validation.enabled)
            self.assertEqual(
                config.variant_validation.front_teeth_only.allowed_labels,
                ("tooth",),
            )
            self.assertFalse(config.save_runtime_ids)
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
            payload["schema_version"] = 6
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "Unsupported.*schema version"):
                CaptureLaunchConfig.load(path)

    def test_schema_v5_loads_explicit_root_pose_playback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["schema_version"] = 5
            payload["root_pose_playback"] = {
                "enabled": True,
                "coordinate_mode": "relative_to_initial",
                "position_interpolation": "linear",
                "orientation_interpolation": "slerp",
                "apply_policy": "authoritative_pose",
                "zero_root_velocity": True,
                "position_tolerance_meters": 0.001,
                "orientation_tolerance_degrees": 0.05,
            }
            config = CaptureLaunchConfig.load(
                self.write_config(Path(temporary), payload)
            )
            self.assertTrue(config.root_pose_playback.enabled)
            self.assertEqual(
                config.root_pose_playback.coordinate_mode,
                "relative_to_initial",
            )
            self.assertEqual(
                config.to_dict()["root_pose_playback"]["orientation_interpolation"],
                "slerp",
            )

    def test_schema_v5_rejects_root_velocity_not_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["schema_version"] = 5
            payload["root_pose_playback"] = {
                "enabled": True,
                "coordinate_mode": "absolute_world",
                "position_interpolation": "linear",
                "orientation_interpolation": "slerp",
                "apply_policy": "authoritative_pose",
                "zero_root_velocity": False,
                "position_tolerance_meters": 0.001,
                "orientation_tolerance_degrees": 0.05,
            }
            with self.assertRaisesRegex(ValueError, "zero_root_velocity must be true"):
                CaptureLaunchConfig.load(self.write_config(Path(temporary), payload))

    def test_schema_v3_uses_safe_transition_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["schema_version"] = 3
            payload.pop("variant_transition")
            payload.pop("variant_validation")
            config = CaptureLaunchConfig.load(
                self.write_config(Path(temporary), payload)
            )
            self.assertEqual(config.variant_transition.settle_render_count, 1)
            self.assertTrue(
                config.variant_transition.restore_full_scene_after_each_frame
            )
            self.assertFalse(config.variant_validation.enabled)

    def test_schema_v3_cannot_silently_ignore_schema_v4_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["schema_version"] = 3
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "cannot contain schema-v4"):
                CaptureLaunchConfig.load(path)

    def test_schema_v3_cannot_enable_front_teeth_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["schema_version"] = 3
            payload.pop("variant_transition")
            payload.pop("variant_validation")
            payload["front_teeth_only_capture"] = {
                "enabled": True,
                "render_prim_paths_config": "front.json",
                "save_rgb": False,
            }
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "requires schema_version 4"):
                CaptureLaunchConfig.load(path)

    def test_requires_full_scene_restore_in_schema_v4(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["variant_transition"][
                "restore_full_scene_after_each_frame"
            ] = False
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "must be true"):
                CaptureLaunchConfig.load(path)

    def test_rejects_required_label_outside_allowed_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["variant_validation"]["front_teeth_only"][
                "required_any_labels"
            ] = ["boom"]
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "contained in allowed_labels"):
                CaptureLaunchConfig.load(path)

    def test_enabled_isolated_capture_requires_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["excavator_only_capture"]["enabled"] = True
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "required when"):
                CaptureLaunchConfig.load(path)

    def test_resolves_isolated_config_from_business_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["excavator_only_capture"] = {
                "enabled": True,
                "render_prim_paths_config": "isolated.json",
            }
            path = self.write_config(Path(temporary), payload)
            config = CaptureLaunchConfig.load(path)
            self.assertEqual(
                config.excavator_only_capture.render_prim_paths_config,
                str((path.parent / "isolated.json").resolve()),
            )

    def test_resolves_front_teeth_config_and_rgb_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["front_teeth_only_capture"] = {
                "enabled": True,
                "render_prim_paths_config": "front_teeth.json",
                "save_rgb": False,
            }
            path = self.write_config(Path(temporary), payload)
            config = CaptureLaunchConfig.load(path)
            self.assertEqual(
                config.front_teeth_only_capture.render_prim_paths_config,
                str((path.parent / "front_teeth.json").resolve()),
            )
            self.assertFalse(config.front_teeth_only_capture.save_rgb)

    def test_disabled_front_teeth_capture_cannot_save_rgb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["front_teeth_only_capture"]["save_rgb"] = True
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "save_rgb must be false"):
                CaptureLaunchConfig.load(path)

    def test_enabled_front_teeth_capture_requires_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["front_teeth_only_capture"] = {
                "enabled": True,
                "render_prim_paths_config": "front.json",
                "save_rgb": False,
            }
            payload["variant_validation"]["enabled"] = False
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "requires variant_validation"):
                CaptureLaunchConfig.load(path)

    def test_rejects_overlapping_image_output_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["image_output_folders"]["full_scene_semantic"] = (
                "full_scene_excavator_rgb/semantic"
            )
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "non-overlapping"):
                CaptureLaunchConfig.load(path)

    def test_rejects_output_folder_inside_reserved_staging_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_payload()
            payload["image_output_folders"]["full_scene_rgb"] = (
                ".frame_staging/full"
            )
            path = self.write_config(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "reserved .frame_staging"):
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
