from __future__ import annotations

import json
from pathlib import Path

def config_payload(output: Path) -> dict:
    return {
        "schema_version": 6,
        "run_id": "test_run",
        "output": str(output),
        "scene": {"usd": "/scene.usda", "physics_hz": 60},
        "render_groups": {
            "camera_main": {
                "kind": "camera_rtx",
                "profile": None,
                "execution": "batched",
                "multi_gpu": False,
                "rt_subframes": 4,
                "warmup_frames": 0,
            }
        },
        "drivers": {},
        "sensors": [
            {
                "id": "front",
                "type": "camera.pinhole",
                "source": {"mode": "existing_prim", "prim_path": "/World/Front"},
                "render_group": "camera_main",
                "clock": {"hz": 10, "phase_seconds": 0, "acquisition": "snapshot"},
                "modalities": ["rgb"],
                "resolution": [640, 480],
                "calibration": {"policy": "read_from_prim"},
                "output": {"sink": "filesystem", "required": True},
            }
        ],
        "capture": {
            "frames": 12,
            "base_hz": 10,
            "capture_initial_frame": True,
            "variant_execution": "variant_major",
            "variants": [{"id": "full_scene", "visibility": {}}],
            "synchronization_groups": [],
        },
        "runtime": {"segment_frames": 5, "worker_command": []},
    }


def write_config(root: Path, payload: dict) -> Path:
    path = root / "run.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
