from __future__ import annotations

import shutil
import uuid
from pathlib import Path


def create_staging_directory(output_root: Path) -> Path:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists():
        raise FileExistsError(f"output_root already exists: {output_root}")
    staging = output_root.parent / f".{output_root.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    return staging


def commit_staging(staging: Path, output_root: Path) -> None:
    if output_root.exists():
        raise FileExistsError(f"output_root appeared during processing: {output_root}")
    staging.replace(output_root)


def discard_staging(staging: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging)
