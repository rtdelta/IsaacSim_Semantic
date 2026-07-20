"""End-to-end pure validation test for a minimal schema-v2 static dataset."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from semantic_mapping import SemanticMapping
from validate_semantic_output import (
    validate_frame_files,
    validate_manifest_v2,
    validate_render_manifest,
    validate_states,
)


class ValidateOutputV2Tests(unittest.TestCase):
    def test_validates_both_renderer_sampling_models(self) -> None:
        realtime = {
            "profile": {"renderer": "RealTimePathTracing"},
            "renderer": {
                "requested": "RealTimePathTracing",
                "effective": "RealTimePathTracing",
            },
            "capture": {"rt_subframes": 16},
            "sampling": {
                "model": "realtime_temporal_subframes",
                "rt_subframes": 16,
                "dlss_exec_mode": 2,
            },
            "mismatches": [],
        }
        pathtracing = {
            "profile": {"renderer": "PathTracing"},
            "renderer": {"requested": "PathTracing", "effective": "PathTracing"},
            "capture": {"rt_subframes": 8},
            "sampling": {
                "model": "path_tracing_spp",
                "spp_per_render_frame": 8,
                "rt_subframes": 8,
                "nominal_spp_per_output": 64,
                "total_spp_cap": 64,
                "planned_spp_per_output": 64,
                "denoiser": True,
                "accumulation_reset_on_time_change": True,
            },
            "mismatches": [],
        }
        validate_render_manifest(realtime)
        validate_render_manifest(pathtracing)

    def test_rejects_renderer_readback_mismatch(self) -> None:
        render = {
            "profile": {"renderer": "PathTracing"},
            "renderer": {
                "requested": "PathTracing",
                "effective": "RealTimePathTracing",
            },
            "capture": {"rt_subframes": 8},
            "sampling": {},
            "mismatches": [],
        }
        with self.assertRaisesRegex(RuntimeError, "did not take effect"):
            validate_render_manifest(render)

    def test_validates_minimal_static_dataset(self) -> None:
        project_dir = Path(__file__).resolve().parents[1]
        mapping_path = project_dir / "configs" / "semantic_mapping_Sim_FangShan_02_native.json"
        mapping = SemanticMapping(mapping_path)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            for folder in (
                "rgb",
                "semantic_id",
                "semantic_color",
                "semantic_runtime_id",
                "metadata",
            ):
                (output / folder).mkdir()

            matrix = [float(index) for index in range(16)]
            states = []
            for frame_id in range(2):
                name = f"{frame_id:04d}"
                ids = np.zeros((2, 3), dtype=np.uint16)
                np.save(output / "semantic_id" / f"semantic_id_{name}.npy", ids)
                np.save(
                    output / "semantic_runtime_id" / f"semantic_runtime_id_{name}.npy",
                    ids.astype(np.uint32),
                )
                Image.fromarray(mapping.colorize(ids)).save(
                    output / "semantic_color" / f"semantic_color_{name}.png"
                )
                Image.fromarray(np.zeros((2, 3, 3), dtype=np.uint8)).save(
                    output / "rgb" / f"rgb_{name}.png"
                )
                metadata = {
                    "schema_version": 2,
                    "frame_id": frame_id,
                    "dataset_time": 0.0,
                    "timeline_time": 0.25,
                    "physics_step": 15,
                    "camera": {"path": "/root/Camera", "world_transform": matrix},
                    "render_product": "SemanticCapture",
                    "resolution": [3, 2],
                    "unknown_labels": [],
                }
                (output / "metadata" / f"frame_{name}.json").write_text(
                    json.dumps(metadata), encoding="utf-8"
                )
                states.append(
                    {
                        **metadata,
                        "motion": {"enabled": False},
                        "camera": {"path": "/root/Camera", "world_transform": matrix},
                    }
                )
            (output / "motion_state.jsonl").write_text(
                "".join(json.dumps(state) + "\n" for state in states),
                encoding="utf-8",
            )

            run_config = {
                "schema_version": 2,
                "status": "complete",
                "frames": 2,
                "resolution": [3, 2],
                "save_runtime_ids": True,
                "physics_hz": 60,
                "capture_fps": 10,
                "capture_initial_frame": True,
                "capture_mode": "static",
                "motion_enabled": False,
                "strict_stage": True,
                "preflight": {"passed": True},
                "render": {"mismatches": []},
                "writer": {"pending": 0, "completed": 2},
            }
            timing = validate_manifest_v2(run_config, expected=2)
            metadata_values = validate_frame_files(
                output, mapping, run_config, expected=2, timing=timing
            )
            moving_bodies, camera_moved = validate_states(
                output, run_config, metadata_values, expected=2, timing=timing
            )
            self.assertEqual(moving_bodies, [])
            self.assertFalse(camera_moved)


if __name__ == "__main__":
    unittest.main()
