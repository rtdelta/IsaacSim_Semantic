from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Sequence, Tuple

from .models import FrameTask


RGB_PREFIX = "rgb_"
RGB_SUFFIX = ".png"
SEMANTIC_PREFIX = "semantic_id_"
SEMANTIC_SUFFIX = ".npy"


def _summarize(frame_ids: Sequence[str], limit: int = 10) -> str:
    visible = ", ".join(frame_ids[:limit])
    remaining = len(frame_ids) - limit
    return f"{visible} (and {remaining} more)" if remaining > 0 else visible


def _discover(
    directory: Path,
    prefix: str,
    suffix: str,
    description: str,
) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.startswith(prefix) or not entry.name.endswith(suffix):
                continue
            frame_id = entry.name[len(prefix) : -len(suffix)]
            if not frame_id:
                raise ValueError(f"{description} filename has no frame id: {entry.name}")
            files[frame_id] = Path(entry.path)
    return files


def discover_frame_tasks(rgb_dir: Path, semantic_dir: Path) -> Tuple[FrameTask, ...]:
    rgb_by_frame = _discover(rgb_dir, RGB_PREFIX, RGB_SUFFIX, "RGB")
    semantic_by_frame = _discover(
        semantic_dir,
        SEMANTIC_PREFIX,
        SEMANTIC_SUFFIX,
        "semantic",
    )
    if not semantic_by_frame:
        raise FileNotFoundError(
            f"no {SEMANTIC_PREFIX}*{SEMANTIC_SUFFIX} files found in {semantic_dir}"
        )

    missing_rgb = sorted(set(semantic_by_frame) - set(rgb_by_frame))
    missing_semantic = sorted(set(rgb_by_frame) - set(semantic_by_frame))
    messages = []
    if missing_rgb:
        messages.append(f"missing RGB frames: {_summarize(missing_rgb)}")
    if missing_semantic:
        messages.append(f"missing semantic frames: {_summarize(missing_semantic)}")
    if messages:
        raise ValueError("RGB and semantic frames do not match; " + "; ".join(messages))

    return tuple(
        FrameTask(
            frame_id=frame_id,
            rgb_path=rgb_by_frame[frame_id],
            semantic_path=semantic_by_frame[frame_id],
        )
        for frame_id in sorted(semantic_by_frame)
    )
