from __future__ import annotations

import csv
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def write_json(path: Path, value: Mapping[str, object]) -> None:
    write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_staging_directory(output_root: Path) -> Path:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        candidate = output_root.parent / (
            f".{output_root.name}.staging-{uuid.uuid4().hex}"
        )
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"cannot allocate staging directory beside {output_root}")


def commit_staging(
    staging_root: Path,
    output_root: Path,
    overwrite: bool,
) -> None:
    staging_root = staging_root.resolve()
    output_root = output_root.resolve()
    if staging_root.parent != output_root.parent:
        raise ValueError("staging and output directories must share a parent")
    if not staging_root.is_dir():
        raise FileNotFoundError(f"staging directory does not exist: {staging_root}")

    if not output_root.exists():
        staging_root.rename(output_root)
        return
    if not overwrite:
        raise FileExistsError(f"output root already exists: {output_root}")

    backup = output_root.parent / (
        f".{output_root.name}.backup-{uuid.uuid4().hex}"
    )
    output_root.rename(backup)
    try:
        staging_root.rename(output_root)
    except BaseException:
        if not output_root.exists() and backup.exists():
            backup.rename(output_root)
        raise
    try:
        shutil.rmtree(backup)
    except OSError:
        # The completed output is already committed. Keep the recoverable backup.
        pass


def materialize_image(source: Path, destination: Path, mode: str) -> None:
    if mode == "none":
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink_required":
        os.link(source, destination)
        return
    if mode == "hardlink_or_copy":
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
        return
    if mode == "symlink":
        os.symlink(source, destination)
        return
    if mode == "copy":
        shutil.copy2(source, destination)
        return
    raise ValueError(f"unsupported image mode: {mode}")
