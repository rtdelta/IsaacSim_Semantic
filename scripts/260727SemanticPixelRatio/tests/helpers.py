from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np


LABELS = (
    "tooth_1_front_3DGS",
    "tooth_2_front_3DGS",
    "tooth_3_front_3DGS",
    "tooth_4_front_3DGS",
    "tooth_5_front_3DGS",
)


def write_mapping(path: Path, dtype: str = "uint16") -> None:
    value = {
        "schema_version": 1,
        "dataset_dtype": dtype,
        "classes": [
            {"label": label, "id": index + 1}
            for index, label in enumerate(LABELS)
        ],
    }
    path.write_text(json.dumps(value), encoding="utf-8")


def write_frames(
    whole_directory: Path,
    reference_directory: Path,
    whole_frames: Sequence[np.ndarray],
    reference_frames: Sequence[np.ndarray],
) -> None:
    whole_directory.mkdir(parents=True)
    reference_directory.mkdir(parents=True)
    for index, array in enumerate(whole_frames):
        np.save(whole_directory / f"semantic_id_{index:04d}.npy", array)
    for index, array in enumerate(reference_frames):
        np.save(reference_directory / f"semantic_id_{index:04d}.npy", array)


def write_config(
    path: Path,
    whole_directory: Path,
    reference_directory: Path,
    mapping: Path,
    output: Path,
) -> None:
    value = {
        "schema_version": 1,
        "inputs": {
            "whole_scene_semantic_dir": str(whole_directory),
            "excavator_only_semantic_dir": str(reference_directory),
            "semantic_mapping": str(mapping),
        },
        "targets": {
            "labels": list(LABELS),
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
            "root": str(output),
            "overwrite": False,
            "resume": True,
            "write_counts_cache": True,
        },
    }
    path.write_text(json.dumps(value), encoding="utf-8")

