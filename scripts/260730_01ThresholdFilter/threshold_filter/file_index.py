from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Tuple

from .config import RunConfig
from .models import FileIndex, ModuleFileIndex, RatioMatrix


PREFIX = "rgb_"
LABEL_SUFFIX = ".txt"
IMAGE_SUFFIX = ".png"


def _scan_module(directory: Path) -> ModuleFileIndex:
    labels: Dict[str, Path] = {}
    images: Dict[str, Path] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            if entry.name == "classes.txt":
                continue
            if entry.name.startswith(PREFIX) and entry.name.endswith(LABEL_SUFFIX):
                frame_id = entry.name[len(PREFIX) : -len(LABEL_SUFFIX)]
                target = labels
            elif entry.name.startswith(PREFIX) and entry.name.endswith(IMAGE_SUFFIX):
                frame_id = entry.name[len(PREFIX) : -len(IMAGE_SUFFIX)]
                target = images
            else:
                continue
            if not frame_id:
                raise ValueError(f"module file has an empty frame ID: {entry.name}")
            if frame_id in target:
                raise ValueError(
                    f"module directory contains duplicate frame ID {frame_id}: "
                    f"{directory}"
                )
            target[frame_id] = Path(entry.path)
    classes_path = directory / "classes.txt"
    if not classes_path.is_file():
        raise FileNotFoundError(f"module classes file does not exist: {classes_path}")
    return ModuleFileIndex(
        labels=labels,
        images=images,
        classes_path=classes_path,
    )


def _summarize(values: Iterable[str], limit: int = 10) -> str:
    items = sorted(values)
    visible = ", ".join(items[:limit])
    if len(items) > limit:
        return f"{visible} (and {len(items) - limit} more)"
    return visible


def build_file_index(config: RunConfig, ratios: RatioMatrix) -> FileIndex:
    tooth = _scan_module(config.inputs.postprocess.tooth_module_dir)
    group = _scan_module(config.inputs.postprocess.group_module_dir)
    ratio_frames = set(ratios.frame_ids)
    tooth_frames = set(tooth.labels)
    missing_tooth = ratio_frames - tooth_frames
    extra_tooth = tooth_frames - ratio_frames
    if missing_tooth or extra_tooth:
        messages = []
        if missing_tooth:
            messages.append(
                "missing tooth label frames: " + _summarize(missing_tooth)
            )
        if extra_tooth:
            messages.append(
                "unexpected tooth label frames: " + _summarize(extra_tooth)
            )
        raise ValueError("tooth labels do not match ratio frames; " + "; ".join(messages))
    extra_group = set(group.labels) - ratio_frames
    if extra_group:
        raise ValueError(
            "group labels contain frames absent from ratio data: "
            + _summarize(extra_group)
        )

    if config.output.image_mode != "none":
        missing_tooth_images = ratio_frames - set(tooth.images)
        if missing_tooth_images:
            raise ValueError(
                "tooth module is missing images required by output mode: "
                + _summarize(missing_tooth_images)
            )
        missing_group_images = set(group.labels) - set(group.images)
        if missing_group_images:
            raise ValueError(
                "group module is missing images required by output mode: "
                + _summarize(missing_group_images)
            )
    return FileIndex(tooth=tooth, group=group)
