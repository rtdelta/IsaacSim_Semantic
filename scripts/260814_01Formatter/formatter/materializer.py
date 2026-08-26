from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Iterator

from .models import MaterializeOperation, MaterializeResult


def materialize_file(
    operation: MaterializeOperation, mode: str
) -> MaterializeResult:
    source = operation.source
    destination = operation.destination
    if source.is_symlink():
        raise ValueError(f"symbolic links are not supported: {source}")
    if not source.is_file():
        raise ValueError(f"source is not a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    actual_mode: str
    if mode == "hardlink_required":
        os.link(source, destination)
        actual_mode = "hardlink"
    elif mode == "hardlink_or_copy":
        try:
            os.link(source, destination)
            actual_mode = "hardlink"
        except OSError:
            shutil.copy2(source, destination)
            actual_mode = "copy"
    elif mode == "copy":
        shutil.copy2(source, destination)
        actual_mode = "copy"
    else:
        raise ValueError(f"unsupported materialization mode: {mode}")

    source_size = source.stat().st_size
    destination_size = destination.stat().st_size
    if source_size != destination_size:
        raise IOError(
            f"materialized size mismatch: {source} ({source_size}) -> "
            f"{destination} ({destination_size})"
        )
    if actual_mode == "hardlink":
        source_stat = source.stat()
        destination_stat = destination.stat()
        if (source_stat.st_dev, source_stat.st_ino) != (
            destination_stat.st_dev,
            destination_stat.st_ino,
        ):
            raise IOError(f"hardlink identity verification failed: {destination}")
    return MaterializeResult(
        category=operation.category,
        source=source,
        destination=destination,
        mode=actual_mode,
        size=destination_size,
    )


def collect_tree_operations(
    *,
    source_root: Path,
    destination_root: Path,
    category: str,
) -> Iterable[MaterializeOperation]:
    if source_root.is_symlink():
        raise ValueError(f"symbolic links are not supported: {source_root}")
    if source_root.is_file():
        return (
            MaterializeOperation(category, source_root, destination_root),
        )
    if not source_root.is_dir():
        raise ValueError(f"source path does not exist: {source_root}")

    operations: list[MaterializeOperation] = []
    for current, directory_names, file_names in os.walk(
        source_root, followlinks=False
    ):
        current_path = Path(current)
        relative = current_path.relative_to(source_root)
        (destination_root / relative).mkdir(parents=True, exist_ok=True)
        for directory_name in directory_names:
            directory_path = current_path / directory_name
            if directory_path.is_symlink():
                raise ValueError(f"symbolic links are not supported: {directory_path}")
        for file_name in file_names:
            source = current_path / file_name
            if source.is_symlink():
                raise ValueError(f"symbolic links are not supported: {source}")
            operations.append(
                MaterializeOperation(
                    category=category,
                    source=source,
                    destination=destination_root / relative / file_name,
                )
            )
    return operations
