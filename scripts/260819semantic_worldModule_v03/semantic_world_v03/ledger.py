"""Append-only commit ledger and atomic run manifest."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import ResumeError


@dataclass(frozen=True)
class LedgerRecord:
    run_id: str
    config_fingerprint: str
    variant_id: str
    frame_id: int
    capture_id: str
    sensor_ids: tuple[str, ...]
    relative_files: tuple[str, ...]
    committed_unix: float

    @property
    def key(self) -> tuple[str, int]:
        return (self.variant_id, self.frame_id)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LedgerRecord":
        return cls(
            run_id=str(value["run_id"]),
            config_fingerprint=str(value["config_fingerprint"]),
            variant_id=str(value["variant_id"]),
            frame_id=int(value["frame_id"]),
            capture_id=str(value["capture_id"]),
            sensor_ids=tuple(value.get("sensor_ids", ())),
            relative_files=tuple(value.get("relative_files", ())),
            committed_unix=float(value["committed_unix"]),
        )


class CommitLedger:
    def __init__(self, output_root: str | Path, *, run_id: str, fingerprint: str) -> None:
        self.output_root = Path(output_root)
        self.run_id = run_id
        self.fingerprint = fingerprint
        self.meta_root = self.output_root / ".v03"
        self.path = self.meta_root / "commits.jsonl"
        self.manifest_path = self.meta_root / "manifest.json"
        self._lock = threading.Lock()
        self.meta_root.mkdir(parents=True, exist_ok=True)
        self._records = self._load()

    def _load(self) -> dict[tuple[str, int], LedgerRecord]:
        records: dict[tuple[str, int], LedgerRecord] = {}
        if not self.path.exists():
            return records
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = LedgerRecord.from_dict(json.loads(line))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ResumeError(f"Invalid ledger record at line {line_number}: {exc}") from exc
            if record.run_id != self.run_id:
                raise ResumeError(
                    f"Output ledger belongs to run {record.run_id}, expected {self.run_id}"
                )
            if record.config_fingerprint != self.fingerprint:
                raise ResumeError("Output ledger configuration fingerprint does not match")
            records[record.key] = record
        return records

    def contains(self, variant_id: str, frame_id: int) -> bool:
        return (variant_id, frame_id) in self._records

    def record(self, value: LedgerRecord) -> None:
        if value.run_id != self.run_id or value.config_fingerprint != self.fingerprint:
            raise ResumeError("Cannot append a record for another run/configuration")
        with self._lock:
            if value.key in self._records:
                return
            encoded = json.dumps(asdict(value), ensure_ascii=False, sort_keys=True) + "\n"
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self._records[value.key] = value

    def committed_keys(self) -> set[tuple[str, int]]:
        return set(self._records)

    def records(self) -> Iterable[LedgerRecord]:
        return tuple(self._records.values())

    def write_manifest(self, status: str, **details: Any) -> None:
        payload = {
            "run_id": self.run_id,
            "config_fingerprint": self.fingerprint,
            "status": status,
            "committed_frames": len(self._records),
            "updated_unix": time.time(),
            **details,
        }
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, self.manifest_path)

