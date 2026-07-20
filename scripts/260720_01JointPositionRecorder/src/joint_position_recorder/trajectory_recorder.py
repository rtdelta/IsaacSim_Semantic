"""Crash-safe CSV recording of articulation read-back joint angles."""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from typing import IO, Any, Mapping, Sequence


class RecorderError(RuntimeError):
    """Raised for unsafe paths, invalid samples, or recorder lifecycle misuse."""


def resolve_csv_path(directory: str | Path, filename: str) -> Path:
    """Resolve a CSV path while rejecting traversal and non-CSV names."""

    name = str(filename).strip()
    if not name or Path(name).name != name:
        raise RecorderError("CSV filename must be a filename without directory components")
    if not name.lower().endswith(".csv"):
        raise RecorderError("CSV filename must end in .csv")
    return (Path(directory).expanduser().resolve() / name).resolve()


class ActualAngleRecorder:
    """Write actual joint angles to a partial file and publish only after validation."""

    def __init__(self, output_path: str | Path, joint_names: Sequence[str]) -> None:
        self.output_path = Path(output_path).expanduser().resolve()
        self.joint_names = tuple(str(name) for name in joint_names)
        if not self.joint_names or len(set(self.joint_names)) != len(self.joint_names):
            raise RecorderError("joint_names must be a non-empty unique sequence")
        if self.output_path.suffix.lower() != ".csv":
            raise RecorderError("output_path must end in .csv")
        self.partial_path = self.output_path.with_name(f"{self.output_path.stem}.partial.csv")
        self.metadata_path = self.output_path.with_name(f"{self.output_path.stem}.metadata.json")
        self.metadata_partial_path = self.output_path.with_name(
            f"{self.output_path.stem}.metadata.partial.json"
        )
        self._stream: IO[str] | None = None
        self._writer: csv.writer | None = None
        self._last_time: float | None = None
        self._sample_count = 0
        self._metadata: dict[str, Any] = {}

    @property
    def active(self) -> bool:
        return self._stream is not None

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def start(
        self,
        initial_positions_degrees: Sequence[float],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if self.active:
            raise RecorderError("Recorder is already active")
        for path in (
            self.output_path,
            self.partial_path,
            self.metadata_path,
            self.metadata_partial_path,
        ):
            if path.exists():
                raise RecorderError(f"Refusing to overwrite existing output: {path}")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.partial_path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._stream, lineterminator="\n")
        self._writer.writerow(("time", *self.joint_names))
        self._metadata = dict(metadata or {})
        self._last_time = None
        self._sample_count = 0
        self.record(0.0, initial_positions_degrees)

    def record(self, elapsed_seconds: float, positions_degrees: Sequence[float]) -> None:
        if not self.active or self._writer is None:
            raise RecorderError("Recorder is not active")
        timestamp = float(elapsed_seconds)
        positions = tuple(float(value) for value in positions_degrees)
        if len(positions) != len(self.joint_names):
            raise RecorderError(
                f"Expected {len(self.joint_names)} positions, got {len(positions)}"
            )
        if not math.isfinite(timestamp) or timestamp < 0:
            raise RecorderError("Sample time must be finite and non-negative")
        if any(not math.isfinite(value) for value in positions):
            raise RecorderError("Joint positions must all be finite")
        if self._last_time is not None and timestamp <= self._last_time:
            raise RecorderError("Sample times must be strictly increasing")
        self._writer.writerow((f"{timestamp:.9f}", *(f"{value:.9f}" for value in positions)))
        self._last_time = timestamp
        self._sample_count += 1

    def stop(self, metadata: Mapping[str, Any] | None = None) -> Path:
        if not self.active or self._stream is None:
            raise RecorderError("Recorder is not active")
        if self._sample_count < 2:
            raise RecorderError("At least two samples are required before publishing a CSV")

        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        self._stream = None
        self._writer = None

        published_metadata = dict(self._metadata)
        published_metadata.update(dict(metadata or {}))
        published_metadata.update(
            {
                "csv": str(self.output_path),
                "joint_order": list(self.joint_names),
                "sample_count": self._sample_count,
                "duration_seconds": self._last_time,
                "completed": True,
            }
        )
        with self.metadata_partial_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(published_metadata, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(self.partial_path, self.output_path)
        os.replace(self.metadata_partial_path, self.metadata_path)
        return self.output_path

    def abort(self) -> Path | None:
        """Close the stream while intentionally retaining any partial CSV."""

        if self._stream is not None:
            self._stream.flush()
            self._stream.close()
            self._stream = None
            self._writer = None
        return self.partial_path if self.partial_path.exists() else None
