"""Create a tiny, deterministic dataset for the tutorial.

Usage from the project directory:

    python docs/tutorials/make_tiny_demo.py
    python run_compare.py --config docs/tutorials/_demo/config.json

Use --root to place generated data elsewhere.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


LABELS = [
    "tooth_1_front_3DGS",
    "tooth_2_front_3DGS",
    "tooth_3_front_3DGS",
    "tooth_4_front_3DGS",
    "tooth_5_front_3DGS",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).with_name("_demo"),
    )
    return parser.parse_args()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_array_if_changed(path: Path, value: np.ndarray) -> None:
    if path.is_file():
        existing = np.load(path, allow_pickle=False)
        if existing.dtype == value.dtype and np.array_equal(existing, value):
            return
    np.save(path, value)


def main() -> int:
    root = parse_args().root.resolve()
    whole_dir = root / "whole"
    reference_dir = root / "reference"
    whole_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    whole_frames = [
        np.asarray([[1, 1, 2, 0], [3, 4, 5, 0]], dtype=np.uint16),
        np.asarray([[1, 0, 0, 0], [0, 0, 0, 0]], dtype=np.uint16),
        np.asarray([[5, 5, 5, 1], [2, 3, 0, 0]], dtype=np.uint16),
    ]
    reference_frames = [
        np.asarray([[1, 2, 2, 0], [3, 5, 5, 0]], dtype=np.uint16),
        np.asarray([[1, 1, 0, 0], [0, 0, 0, 0]], dtype=np.uint16),
        np.asarray([[5, 5, 0, 1], [2, 4, 0, 0]], dtype=np.uint16),
    ]
    for index, (whole, reference) in enumerate(
        zip(whole_frames, reference_frames)
    ):
        name = f"semantic_id_{index:04d}.npy"
        save_array_if_changed(whole_dir / name, whole)
        save_array_if_changed(reference_dir / name, reference)

    write_json(
        root / "mapping.json",
        {
            "schema_version": 1,
            "dataset_dtype": "uint16",
            "classes": [
                {"label": label, "id": index + 1}
                for index, label in enumerate(LABELS)
            ],
        },
    )
    write_json(
        root / "config.json",
        {
            "schema_version": 1,
            "inputs": {
                "whole_scene_semantic_dir": "whole",
                "excavator_only_semantic_dir": "reference",
                "semantic_mapping": "mapping.json",
            },
            "targets": {
                "labels": LABELS,
                "group_name": "tooth_front_group",
            },
            "ratio": {
                "numerator": "whole_scene",
                "denominator": "excavator_only",
                "zero_denominator": "null",
                "over_one": "keep_and_flag",
            },
            "pairing": {"mode": "strict"},
            "execution": {
                "backend": "numpy",
                "batch_frames": 2,
                "reader_threads": 2,
                "ring_slots": 2,
                "cpu_workers": 2,
                "device": "cuda",
                "on_frame_error": "fail_fast",
                "verify_sample_frames": 0,
            },
            "output": {
                "root": "output",
                "overwrite": False,
                "resume": True,
                "write_counts_cache": True,
            },
        },
    )
    print(f"tutorial dataset written to: {root}")
    print(f"config: {root / 'config.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
