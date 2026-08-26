from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conftest import config_payload, write_config
from semantic_world_v03.config import load_run_config
from semantic_world_v03.errors import ConfigurationError
from semantic_world_v03.timing import CaptureTimeline


class ConfigAndTimingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_existing_fisheye_uses_prim_calibration_policy(self):
        payload = config_payload(self.root / "out")
        payload["sensors"][0]["type"] = "camera.fisheye_opencv"
        payload["sensors"][0]["calibration"] = {
            "policy": "read_and_validate",
            "expected_model": "opencv_fisheye",
        }
        config = load_run_config(write_config(self.root, payload))
        sensor = config.sensor("front")
        self.assertEqual(sensor.source.prim_path, "/World/Front")
        self.assertIsNone(sensor.calibration.profile)
        self.assertEqual(sensor.calibration.policy, "read_and_validate")

    def test_timeline_is_integer_and_multi_rate(self):
        payload = config_payload(self.root / "out")
        slower = dict(payload["sensors"][0])
        slower["id"] = "slow"
        slower["source"] = {"mode": "existing_prim", "prim_path": "/World/Slow"}
        slower["clock"] = {"hz": 5, "phase_seconds": 0, "acquisition": "snapshot"}
        payload["sensors"].append(slower)
        timeline = CaptureTimeline(load_run_config(write_config(self.root, payload)))
        self.assertEqual(timeline.physics_step_for_frame(3), 18)
        self.assertEqual([item.sensor_id for item in timeline.due_for_frame(1)], ["front"])
        self.assertEqual(
            {item.sensor_id for item in timeline.due_for_frame(2)}, {"front", "slow"}
        )

    def test_phase_must_align_to_physics_step(self):
        payload = config_payload(self.root / "out")
        payload["sensors"][0]["clock"]["phase_seconds"] = 0.01
        with self.assertRaisesRegex(ConfigurationError, "align"):
            load_run_config(write_config(self.root, payload))

    def test_frame_major_rejects_multi_variant_interval_sensor(self):
        payload = config_payload(self.root / "out")
        payload["render_groups"]["lidar"] = {
            "kind": "rtx_sensor", "profile": None, "execution": "batched",
            "multi_gpu": False, "rt_subframes": 1, "warmup_frames": 0,
        }
        payload["sensors"].append(
            {
                "id": "lidar", "type": "lidar.rtx.rotary",
                "source": {"mode": "existing_prim", "prim_path": "/World/Lidar"},
                "render_group": "lidar",
                "clock": {"hz": 10, "acquisition": "interval"},
                "modalities": ["point_cloud"],
                "calibration": {"policy": "read_from_prim"},
                "output": {"sink": "filesystem", "required": True},
            }
        )
        payload["capture"]["variant_execution"] = "frame_major"
        payload["capture"]["variants"].append({"id": "isolated", "visibility": {}})
        with self.assertRaisesRegex(ConfigurationError, "independent interval"):
            load_run_config(write_config(self.root, payload))

    def test_interval_sensor_waits_for_first_complete_period(self):
        payload = config_payload(self.root / "out")
        payload["render_groups"]["lidar"] = {
            "kind": "rtx_sensor", "profile": None, "execution": "batched",
            "multi_gpu": False, "rt_subframes": 1, "warmup_frames": 0,
        }
        payload["sensors"].append(
            {
                "id": "lidar", "type": "lidar.rtx.rotary",
                "source": {"mode": "existing_prim", "prim_path": "/World/Lidar"},
                "render_group": "lidar",
                "clock": {"hz": 10, "phase_seconds": 0, "acquisition": "interval"},
                "modalities": ["range"],
                "calibration": {"policy": "read_from_prim"},
                "output": {"sink": "filesystem", "required": True},
            }
        )
        timeline = CaptureTimeline(load_run_config(write_config(self.root, payload)))
        self.assertNotIn("lidar", {item.sensor_id for item in timeline.due_for_frame(0)})
        lidar_due = next(
            item for item in timeline.due_for_frame(1) if item.sensor_id == "lidar"
        )
        self.assertEqual((lidar_due.interval_start, lidar_due.interval_end), (0.0, 0.1))

    def test_variant_include_paths_and_modalities_are_strictly_loaded(self):
        payload = config_payload(self.root / "out")
        payload["sensors"][0]["modalities"] = ["rgb", "semantic_segmentation"]
        payload["capture"]["variants"] = [
            {
                "id": "excavator_only",
                "include_paths": ["/World/Excavator"],
                "visibility": {"/World/Light": "inherited"},
                "modalities_by_sensor": {"front": ["semantic_segmentation"]},
            }
        ]
        config = load_run_config(write_config(self.root, payload))
        variant = config.variant("excavator_only")
        self.assertEqual(variant.include_paths, ("/World/Excavator",))
        self.assertEqual(
            variant.modalities_for(config.sensor("front")),
            ("semantic_segmentation",),
        )

    def test_variant_rejects_unconfigured_modality(self):
        payload = config_payload(self.root / "out")
        payload["capture"]["variants"][0]["modalities_by_sensor"] = {
            "front": ["semantic_segmentation"]
        }
        with self.assertRaisesRegex(ConfigurationError, "not configured"):
            load_run_config(write_config(self.root, payload))

    def test_variant_rejects_unknown_fields(self):
        payload = config_payload(self.root / "out")
        payload["capture"]["variants"][0]["include"] = ["/World/Excavator"]
        with self.assertRaisesRegex(ConfigurationError, "Unknown capture.variants"):
            load_run_config(write_config(self.root, payload))


if __name__ == "__main__":
    unittest.main()
