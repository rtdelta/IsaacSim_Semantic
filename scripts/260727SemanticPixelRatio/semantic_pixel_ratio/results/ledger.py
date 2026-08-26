from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from ..models import BatchCounts, CountLedgerData
from .atomic_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class CountsLedger:
    def __init__(
        self,
        output_root: Path,
        config_fingerprint: str,
        expected_frames: int,
        target_labels: Sequence[str],
        backend_name: str,
        resume: bool,
    ) -> None:
        self.output_root = output_root
        self.parts_directory = output_root / "counts"
        self.manifest_path = output_root / "counts_manifest.json"
        self.parts_directory.mkdir(parents=True, exist_ok=True)
        self._config_fingerprint = config_fingerprint
        self._expected_frames = expected_frames
        self._target_labels = tuple(target_labels)
        self._backend_name = backend_name

        if self.manifest_path.exists():
            if not resume:
                raise FileExistsError(
                    f"counts manifest already exists: {self.manifest_path}"
                )
            self._manifest = self._load_and_validate_manifest()
        else:
            existing_parts = list(self.parts_directory.glob("part-*.npz"))
            if existing_parts:
                raise ValueError(
                    "counts parts exist without a manifest; use a new output root"
                )
            self._manifest = {
                "schema_version": 1,
                "status": "running",
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "config_fingerprint": config_fingerprint,
                "expected_frames": expected_frames,
                "completed_frames": 0,
                "target_labels": list(target_labels),
                "backend": backend_name,
                "parts": [],
            }
            atomic_write_json(self.manifest_path, self._manifest)

    def _load_and_validate_manifest(self) -> Dict[str, object]:
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"cannot resume unreadable counts manifest: {self.manifest_path}"
            ) from exc
        if manifest.get("schema_version") != 1:
            raise ValueError("unsupported counts manifest schema")
        if manifest.get("config_fingerprint") != self._config_fingerprint:
            raise ValueError(
                "output contains counts for a different input or target configuration"
            )
        if manifest.get("expected_frames") != self._expected_frames:
            raise ValueError("counts manifest frame total does not match current input")
        if tuple(manifest.get("target_labels", [])) != self._target_labels:
            raise ValueError("counts manifest target labels do not match current config")

        completed = 0
        for part in manifest.get("parts", []):
            if not isinstance(part, dict):
                raise ValueError("counts manifest contains an invalid part")
            path = self.parts_directory / str(part.get("file", ""))
            if not path.is_file():
                raise FileNotFoundError(f"counts part is missing: {path}")
            if _sha256(path) != part.get("sha256"):
                raise ValueError(f"counts part checksum mismatch: {path}")
            if int(part.get("start_ordinal", -1)) != completed:
                raise ValueError("counts parts are not contiguous")
            completed += int(part.get("frames", 0))
        if completed != int(manifest.get("completed_frames", -1)):
            raise ValueError("counts manifest completed frame count is inconsistent")
        manifest["status"] = "running"
        manifest["updated_at"] = _utc_now()
        manifest["backend"] = self._backend_name
        atomic_write_json(self.manifest_path, manifest)
        return manifest

    @property
    def completed_frames(self) -> int:
        return int(self._manifest["completed_frames"])

    def append(self, result: BatchCounts) -> None:
        if not result.pairs:
            return
        start = self.completed_frames
        expected_ordinals = list(range(start, start + len(result.pairs)))
        actual_ordinals = [pair.ordinal for pair in result.pairs]
        if actual_ordinals != expected_ordinals:
            raise ValueError(
                "batch ordinals are not the next contiguous ledger range"
            )
        if np.any(result.counts < 0):
            raise ValueError("pixel counts must not be negative")

        end = start + len(result.pairs) - 1
        file_name = f"part-{start:09d}-{end:09d}.npz"
        final_path = self.parts_directory / file_name
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{file_name}.",
            suffix=".tmp",
            dir=self.parts_directory,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                np.savez(
                    handle,
                    ordinals=np.asarray(actual_ordinals, dtype=np.int64),
                    frame_ids=np.asarray(
                        [pair.frame_id for pair in result.pairs],
                        dtype=np.str_,
                    ),
                    whole_counts=np.asarray(
                        result.counts[:, 0, :],
                        dtype=np.uint32,
                    ),
                    reference_counts=np.asarray(
                        result.counts[:, 1, :],
                        dtype=np.uint32,
                    ),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, final_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

        part = {
            "file": file_name,
            "start_ordinal": start,
            "end_ordinal": end,
            "frames": len(result.pairs),
            "sha256": _sha256(final_path),
        }
        parts = list(self._manifest["parts"])
        parts.append(part)
        self._manifest["parts"] = parts
        self._manifest["completed_frames"] = end + 1
        self._manifest["updated_at"] = _utc_now()
        atomic_write_json(self.manifest_path, self._manifest)

    def load_all(self) -> CountLedgerData:
        ordinals: List[np.ndarray] = []
        frame_ids: List[str] = []
        whole_counts: List[np.ndarray] = []
        reference_counts: List[np.ndarray] = []
        for part in self._manifest["parts"]:
            path = self.parts_directory / str(part["file"])
            with np.load(path, allow_pickle=False) as archive:
                ordinals.append(np.asarray(archive["ordinals"], dtype=np.int64))
                frame_ids.extend(str(item) for item in archive["frame_ids"])
                whole_counts.append(
                    np.asarray(archive["whole_counts"], dtype=np.uint32)
                )
                reference_counts.append(
                    np.asarray(archive["reference_counts"], dtype=np.uint32)
                )
        if not ordinals:
            return CountLedgerData(
                ordinals=np.empty((0,), dtype=np.int64),
                frame_ids=(),
                whole_counts=np.empty((0, 5), dtype=np.uint32),
                reference_counts=np.empty((0, 5), dtype=np.uint32),
            )
        return CountLedgerData(
            ordinals=np.concatenate(ordinals),
            frame_ids=tuple(frame_ids),
            whole_counts=np.concatenate(whole_counts, axis=0),
            reference_counts=np.concatenate(reference_counts, axis=0),
        )

    def mark_completed(self) -> None:
        if self.completed_frames != self._expected_frames:
            raise ValueError(
                f"cannot complete ledger: {self.completed_frames}/"
                f"{self._expected_frames} frames are present"
            )
        self._manifest["status"] = "completed"
        self._manifest["updated_at"] = _utc_now()
        self._manifest["completed_at"] = _utc_now()
        atomic_write_json(self.manifest_path, self._manifest)

    def mark_failed(self, message: str) -> None:
        self._manifest["status"] = "failed"
        self._manifest["updated_at"] = _utc_now()
        self._manifest["last_error"] = message
        atomic_write_json(self.manifest_path, self._manifest)

