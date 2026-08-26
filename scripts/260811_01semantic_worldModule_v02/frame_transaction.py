"""Pure filesystem transaction for publishing all variants of one frame."""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Iterable

from capture_context import CaptureReceipt, CaptureVariant


class FrameStagingTransaction:
    """Move fully written staged files into final dataset paths as one frame."""

    def __init__(
        self,
        output_path: str | Path,
        *,
        frame_padding: int = 4,
        allow_overwrite: bool = False,
    ) -> None:
        self._output_path = Path(output_path).resolve()
        self._frame_padding = int(frame_padding)
        if self._frame_padding < 1:
            raise ValueError("frame_padding must be greater than or equal to 1")
        self._allow_overwrite = bool(allow_overwrite)
        self._committed_frames: set[int] = set()

    @property
    def committed_frame_count(self) -> int:
        return len(self._committed_frames)

    def staging_prefix(self, frame_id: int) -> str:
        frame_name = f"{int(frame_id):0{self._frame_padding}d}"
        return str(PurePosixPath(".frame_staging", f"frame_{frame_name}"))

    def staged_path(self, frame_id: int, final_path: str) -> str:
        return str(PurePosixPath(self.staging_prefix(frame_id), final_path))

    def _safe_output_path(self, relative_path: str) -> Path:
        path = (self._output_path / Path(relative_path)).resolve()
        if not path.is_relative_to(self._output_path):
            raise RuntimeError(f"Output path escapes configured root: {relative_path}")
        return path

    def commit(
        self,
        frame_id: int,
        receipts: Iterable[CaptureReceipt],
    ) -> None:
        frame_id = int(frame_id)
        if frame_id in self._committed_frames:
            raise RuntimeError(f"Frame {frame_id} was committed more than once")
        receipt_list = tuple(receipts)
        if not receipt_list:
            raise ValueError("At least one CaptureReceipt is required to commit a frame")
        if any(receipt.frame_id != frame_id for receipt in receipt_list):
            raise RuntimeError("Cannot commit receipts from different frame IDs")
        variants = [receipt.variant for receipt in receipt_list]
        if len(variants) != len(set(variants)):
            raise RuntimeError(f"Frame {frame_id} contains duplicate capture variants")
        if CaptureVariant.FULL_SCENE not in variants:
            raise RuntimeError(f"Frame {frame_id} cannot commit without full_scene")

        file_pairs = tuple(
            pair for receipt in receipt_list for pair in receipt.staged_files
        )
        if not file_pairs:
            raise RuntimeError(f"Frame {frame_id} has no staged files to commit")
        staged_paths = [staged for staged, _final in file_pairs]
        final_paths = [final for _staged, final in file_pairs]
        if len(staged_paths) != len(set(staged_paths)):
            raise RuntimeError(f"Frame {frame_id} contains duplicate staged paths")
        if len(final_paths) != len(set(final_paths)):
            raise RuntimeError(f"Frame {frame_id} contains duplicate final paths")

        expected_stage_root = self._safe_output_path(self.staging_prefix(frame_id))
        global_stage_root = self._safe_output_path(".frame_staging")
        resolved_pairs: list[tuple[Path, Path]] = []
        backup_pairs: list[tuple[Path, Path]] = []
        for staged, final in file_pairs:
            source = self._safe_output_path(staged)
            destination = self._safe_output_path(final)
            if not source.is_relative_to(expected_stage_root):
                raise RuntimeError(f"Staged path is outside frame transaction: {staged}")
            if not source.is_file():
                raise RuntimeError(f"Staged output is missing: {source}")
            if destination.is_relative_to(global_stage_root):
                raise RuntimeError(f"Final output cannot be inside .frame_staging: {final}")
            if destination.exists() and not self._allow_overwrite:
                raise RuntimeError(f"Final output already exists: {destination}")
            if destination.exists():
                relative_destination = destination.relative_to(self._output_path)
                backup = expected_stage_root / "__previous__" / relative_destination
                if backup.exists():
                    raise RuntimeError(f"Overwrite backup already exists: {backup}")
                backup_pairs.append((destination, backup))
            resolved_pairs.append((source, destination))

        moved: list[tuple[Path, Path]] = []
        backed_up: list[tuple[Path, Path]] = []
        try:
            for destination, backup in backup_pairs:
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, backup)
                backed_up.append((destination, backup))
            for source, destination in resolved_pairs:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
                moved.append((source, destination))
        except Exception:
            for source, destination in reversed(moved):
                if destination.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, source)
            for destination, backup in reversed(backed_up):
                if backup.exists() and not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(backup, destination)
            raise

        if expected_stage_root.exists():
            shutil.rmtree(expected_stage_root)
        self._committed_frames.add(frame_id)

    def discard(self, frame_id: int) -> None:
        stage_root = self._safe_output_path(self.staging_prefix(int(frame_id)))
        if stage_root.exists():
            shutil.rmtree(stage_root)
