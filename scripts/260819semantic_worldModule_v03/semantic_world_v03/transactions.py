"""Filesystem frame transactions: stage, validate, atomically publish, then ledger."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from .errors import TransactionError


class FrameTransaction:
    def __init__(self, output_root: str | Path, variant_id: str, frame_id: int) -> None:
        self.output_root = Path(output_root).resolve()
        token = uuid.uuid4().hex
        self.stage_root = (
            self.output_root / ".v03" / "transactions" / variant_id / f"{frame_id:08d}-{token}"
        )
        self.variant_id = variant_id
        self.frame_id = frame_id
        self._files: list[Path] = []
        self._closed = False
        self.stage_root.mkdir(parents=True, exist_ok=False)

    def path(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise TransactionError(f"Unsafe transaction path: {relative}")
        target = (self.stage_root / relative).resolve()
        if self.stage_root not in target.parents:
            raise TransactionError(f"Transaction path escapes staging root: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target not in self._files:
            self._files.append(target)
        return target

    def commit(self) -> tuple[str, ...]:
        if self._closed:
            raise TransactionError("Transaction is already closed")
        relative_files: list[str] = []
        try:
            for staged in self._files:
                if not staged.is_file():
                    raise TransactionError(f"Expected staged file was not written: {staged}")
                relative = staged.relative_to(self.stage_root)
                destination = self.output_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, destination)
                relative_files.append(relative.as_posix())
        except Exception:
            self.rollback()
            raise
        self._closed = True
        shutil.rmtree(self.stage_root, ignore_errors=True)
        return tuple(sorted(relative_files))

    def rollback(self) -> None:
        if not self._closed:
            shutil.rmtree(self.stage_root, ignore_errors=True)
            self._closed = True

    def __enter__(self) -> "FrameTransaction":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is not None:
            self.rollback()

