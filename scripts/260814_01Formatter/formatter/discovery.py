from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from .models import DatasetContract, FrameFiles


@dataclass(frozen=True)
class _DiscoveredFile:
    frame_token: str
    path: Path


def _extract_frame_token(path: Path) -> str:
    stem = path.stem
    if "_" not in stem:
        raise ValueError(f"file name has no '_<frame_id>' suffix: {path}")
    prefix, frame_token = stem.rsplit("_", 1)
    if not prefix or not frame_token or not frame_token.isdecimal():
        raise ValueError(f"file name has invalid numeric frame ID: {path}")
    return frame_token


def _scan_frame_directory(
    directory: Path,
    *,
    category: str,
    required_suffix: str | None,
    skip_classes: bool,
) -> Dict[int, _DiscoveredFile]:
    if not directory.is_dir():
        raise ValueError(f"missing {category} directory: {directory}")
    values: Dict[int, _DiscoveredFile] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                raise ValueError(f"symbolic links are not supported in {category}: {path}")
            if not entry.is_file(follow_symlinks=False):
                raise ValueError(f"unexpected non-file in {category}: {path}")
            if skip_classes and entry.name == "classes.txt":
                continue
            if required_suffix is not None and path.suffix.lower() != required_suffix:
                raise ValueError(
                    f"unexpected file extension in {category}: {path}; "
                    f"expected {required_suffix}"
                )
            if not path.suffix:
                raise ValueError(f"file has no extension in {category}: {path}")
            token = _extract_frame_token(path)
            numeric = int(token, 10)
            previous = values.get(numeric)
            if previous is not None:
                raise ValueError(
                    f"duplicate numeric frame ID {numeric} in {category}: "
                    f"{previous.path} and {path}"
                )
            values[numeric] = _DiscoveredFile(token, path)
    if not values:
        raise ValueError(f"no frame files found in {category}: {directory}")
    return values


def _describe_ids(values: set[int], limit: int = 10) -> str:
    ordered = sorted(values)
    shown = ", ".join(str(value) for value in ordered[:limit])
    suffix = " ..." if len(ordered) > limit else ""
    return f"count={len(ordered)} [{shown}{suffix}]"


def discover_dataset(input_root: Path) -> DatasetContract:
    dataset_root = input_root / "dataset"
    rgb_dir = dataset_root / "rgb"
    tooth_dir = dataset_root / "tooth_boxes"
    collision_dir = dataset_root / "tooth_collision_model"

    if dataset_root.is_symlink() or not dataset_root.is_dir():
        raise ValueError(f"missing or symbolic dataset directory: {dataset_root}")
    expected_entries = {"rgb", "tooth_boxes", "tooth_collision_model"}
    actual_entries = {entry.name for entry in dataset_root.iterdir()}
    unexpected_entries = sorted(actual_entries - expected_entries)
    if unexpected_entries:
        raise ValueError(
            "unexpected entries in dataset root: " + ", ".join(unexpected_entries)
        )
    for directory in (rgb_dir, tooth_dir, collision_dir):
        if directory.is_symlink():
            raise ValueError(f"symbolic dataset directories are not supported: {directory}")

    for classes_path in (tooth_dir / "classes.txt", collision_dir / "classes.txt"):
        if classes_path.is_symlink() or not classes_path.is_file():
            raise ValueError(f"missing source classes file: {classes_path}")

    rgb = _scan_frame_directory(
        rgb_dir,
        category="RGB",
        required_suffix=None,
        skip_classes=False,
    )
    tooth = _scan_frame_directory(
        tooth_dir,
        category="tooth labels",
        required_suffix=".txt",
        skip_classes=True,
    )
    collision = _scan_frame_directory(
        collision_dir,
        category="collision labels",
        required_suffix=".txt",
        skip_classes=True,
    )

    rgb_ids = set(rgb)
    tooth_ids = set(tooth)
    collision_ids = set(collision)
    if rgb_ids != tooth_ids or rgb_ids != collision_ids:
        details = [
            f"missing tooth labels: {_describe_ids(rgb_ids - tooth_ids)}",
            f"extra tooth labels: {_describe_ids(tooth_ids - rgb_ids)}",
            f"missing collision labels: {_describe_ids(rgb_ids - collision_ids)}",
            f"extra collision labels: {_describe_ids(collision_ids - rgb_ids)}",
        ]
        raise ValueError("frame sets do not match; " + "; ".join(details))

    ordered_ids = sorted(rgb_ids)
    max_frame_id = ordered_ids[-1]
    padding_width = len(str(max_frame_id))
    frames: Tuple[FrameFiles, ...] = tuple(
        FrameFiles(
            numeric_frame_id=frame_id,
            rgb_frame_token=rgb[frame_id].frame_token,
            tooth_frame_token=tooth[frame_id].frame_token,
            collision_frame_token=collision[frame_id].frame_token,
            rgb_path=rgb[frame_id].path,
            tooth_label_path=tooth[frame_id].path,
            collision_label_path=collision[frame_id].path,
        )
        for frame_id in ordered_ids
    )
    return DatasetContract(
        frames=frames,
        max_frame_id=max_frame_id,
        padding_width=padding_width,
    )
