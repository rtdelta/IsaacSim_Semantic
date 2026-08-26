from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple

from .models import FramePair


PREFIX = "semantic_id_"
SUFFIX = ".npy"


def _discover(directory: Path) -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if (
                not entry.is_file()
                or not entry.name.startswith(PREFIX)
                or not entry.name.endswith(SUFFIX)
            ):
                continue
            frame_id = entry.name[len(PREFIX) : -len(SUFFIX)]
            if not frame_id:
                raise ValueError(f"semantic filename has no frame ID: {entry.name}")
            if frame_id in found:
                raise ValueError(f"duplicate semantic frame ID: {frame_id}")
            found[frame_id] = Path(entry.path)
    if not found:
        raise FileNotFoundError(
            f"no {PREFIX}*{SUFFIX} files found in {directory}"
        )
    return found


def _summarize(values: Iterable[str], limit: int = 10) -> str:
    items = sorted(values)
    visible = ", ".join(items[:limit])
    if len(items) > limit:
        return f"{visible} (and {len(items) - limit} more)"
    return visible


def _frame_sort_key(frame_id: str) -> Tuple[int, object]:
    if frame_id.isdigit():
        return (0, int(frame_id))
    return (1, frame_id)


def discover_frame_pairs(
    whole_directory: Path,
    reference_directory: Path,
) -> Tuple[FramePair, ...]:
    whole = _discover(whole_directory)
    reference = _discover(reference_directory)
    missing_reference = set(whole) - set(reference)
    missing_whole = set(reference) - set(whole)
    messages = []
    if missing_reference:
        messages.append(
            "missing excavator-only frames: "
            + _summarize(missing_reference)
        )
    if missing_whole:
        messages.append(
            "missing whole-scene frames: " + _summarize(missing_whole)
        )
    if messages:
        raise ValueError("semantic frame sets do not match; " + "; ".join(messages))

    frame_ids = sorted(whole, key=_frame_sort_key)
    return tuple(
        FramePair(
            ordinal=ordinal,
            frame_id=frame_id,
            whole_path=whole[frame_id],
            reference_path=reference[frame_id],
        )
        for ordinal, frame_id in enumerate(frame_ids)
    )


def fingerprint_pairs(pairs: Sequence[FramePair]) -> str:
    digest = hashlib.sha256()
    for pair in pairs:
        digest.update(pair.frame_id.encode("utf-8"))
        digest.update(b"\0")
        for path in (pair.whole_path, pair.reference_path):
            stat = path.stat()
            digest.update(str(path).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(b"\0")
    return digest.hexdigest()

