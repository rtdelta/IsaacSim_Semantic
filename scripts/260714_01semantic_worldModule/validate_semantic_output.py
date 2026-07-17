"""Validate file counts, semantic color reconstruction, and recorded motion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from semantic_mapping import SemanticMapping


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def changed(values: list[list[float] | None], tolerance: float = 1e-7) -> bool:
    present = [np.asarray(value, dtype=np.float64) for value in values if value is not None]
    if len(present) < 2:
        return False
    return any(not np.allclose(present[0], value, atol=tolerance, rtol=0.0) for value in present[1:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--expected-frames", type=int, default=50)
    args = parser.parse_args()

    output = Path(args.output)
    mapping = SemanticMapping(args.mapping)
    run_config = load_json(output / "run_config.json")
    expected = args.expected_frames
    expected_shape = (int(run_config["resolution"][1]), int(run_config["resolution"][0]))
    valid_ids = {0, 65535, *(int(entry["id"]) for entry in mapping.schema["classes"])}

    required_patterns = {
        "rgb": "rgb_*.png",
        "semantic_id": "semantic_id_*.npy",
        "semantic_color": "semantic_color_*.png",
        "semantic_runtime_id": "semantic_runtime_id_*.npy",
        "metadata": "frame_*.json",
    }
    for folder, pattern in required_patterns.items():
        count = len(list((output / folder).glob(pattern)))
        if count != expected:
            raise RuntimeError(f"{folder} contains {count} frame files, expected {expected}")

    for frame_id in range(expected):
        frame_name = f"{frame_id:04d}"
        dataset_ids = np.load(output / "semantic_id" / f"semantic_id_{frame_name}.npy")
        if dataset_ids.shape != expected_shape or dataset_ids.dtype != np.uint16:
            raise RuntimeError(
                f"Frame {frame_id}: invalid semantic ID array {dataset_ids.shape} {dataset_ids.dtype}"
            )
        unknown_ids = set(int(value) for value in np.unique(dataset_ids)) - valid_ids
        if unknown_ids:
            raise RuntimeError(f"Frame {frame_id}: undefined semantic IDs {sorted(unknown_ids)}")
        saved_color = np.asarray(
            Image.open(output / "semantic_color" / f"semantic_color_{frame_name}.png").convert("RGB")
        )
        if not np.array_equal(saved_color, mapping.colorize(dataset_ids)):
            raise RuntimeError(f"Frame {frame_id}: semantic color PNG does not match semantic ID NPY")
        metadata = load_json(output / "metadata" / f"frame_{frame_name}.json")
        if metadata.get("unknown_labels"):
            raise RuntimeError(f"Frame {frame_id}: unknown labels {metadata['unknown_labels']}")

    with (output / "motion_state.jsonl").open("r", encoding="utf-8") as stream:
        states = [json.loads(line) for line in stream if line.strip()]
    if len(states) != expected:
        raise RuntimeError(f"motion_state.jsonl contains {len(states)} states, expected {expected}")

    joint_limits = {entry["name"]: entry for entry in run_config.get("joints", [])}
    for state in states:
        for name, target in state["motion"].get("target_degrees", {}).items():
            joint = joint_limits[name]
            if not joint["lower_limit_degrees"] <= target <= joint["upper_limit_degrees"]:
                raise RuntimeError(f"Joint {name} target is outside limits: {target}")

    transforms_by_body: dict[str, list[list[float] | None]] = {}
    for state in states:
        for name, transform in state["motion"].get("body_world_transform", {}).items():
            transforms_by_body.setdefault(name, []).append(transform)
    moving_bodies = sorted(name for name, values in transforms_by_body.items() if changed(values))
    if not moving_bodies:
        raise RuntimeError("No controlled body world transform changed across the capture")
    camera_transforms = [state["camera"].get("world_transform") for state in states]
    if not changed(camera_transforms):
        raise RuntimeError("Camera world transform did not change with the cab")

    print(
        f"[validation] PASS: {expected} frames, semantic mapping consistent, "
        f"moving bodies={moving_bodies}, camera moved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
