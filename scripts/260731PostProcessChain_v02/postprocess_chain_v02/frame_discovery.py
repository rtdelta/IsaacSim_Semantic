from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Tuple

from .config import RunConfig
from .models import FrameTask


def _discover(directory: Path, prefix: str, suffix: str) -> Dict[str, Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"input directory does not exist: {directory}")
    values: Dict[str, Path] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            name = entry.name
            if not name.startswith(prefix) or not name.endswith(suffix):
                continue
            frame_id = name[len(prefix) : -len(suffix)]
            if not frame_id:
                raise ValueError(f"input file has empty frame ID: {entry.path}")
            if frame_id in values:
                raise ValueError(
                    f"duplicate frame ID {frame_id!r} in directory {directory}"
                )
            values[frame_id] = Path(entry.path)
    if not values:
        raise ValueError(
            f"no files matching {prefix}*{suffix} in input directory {directory}"
        )
    return values


def _sort_key(frame_id: str) -> Tuple[int, object]:
    return (0, int(frame_id)) if frame_id.isdigit() else (1, frame_id)


def _summarize(values: Iterable[str], limit: int = 10) -> str:
    items = sorted(values, key=_sort_key)
    visible = ", ".join(items[:limit])
    if len(items) > limit:
        visible += f" (and {len(items) - limit} more)"
    return visible


def discover_frame_tasks(config: RunConfig) -> Tuple[FrameTask, ...]:
    rgb = _discover(config.inputs.full_scene.rgb_dir, "rgb_", ".png")
    full = _discover(config.inputs.full_scene.semantic_dir, "semantic_id_", ".npy")
    reference = _discover(
        config.inputs.reference.semantic_dir,
        "semantic_id_",
        ".npy",
    )
    rgb_ids = set(rgb)
    full_ids = set(full)
    reference_ids = set(reference)
    if rgb_ids != full_ids or rgb_ids != reference_ids:
        messages = []
        for name, values in (
            ("missing full semantic", rgb_ids - full_ids),
            ("extra full semantic", full_ids - rgb_ids),
            ("missing reference semantic", rgb_ids - reference_ids),
            ("extra reference semantic", reference_ids - rgb_ids),
        ):
            if values:
                messages.append(f"{name}: {_summarize(values)}")
        raise ValueError("strict frame pairing failed; " + "; ".join(messages))
    frame_ids = tuple(sorted(rgb_ids, key=_sort_key))
    return tuple(
        FrameTask(
            ordinal=index,
            frame_id=frame_id,
            full_rgb_path=rgb[frame_id],
            full_semantic_path=full[frame_id],
            reference_semantic_path=reference[frame_id],
        )
        for index, frame_id in enumerate(frame_ids)
    )
