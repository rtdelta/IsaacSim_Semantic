"""Crash-safe CSV recording for excavator joint targets."""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import IO, Mapping

from trajectory import CSV_COLUMNS, JOINT_NAMES, JointTrajectory, normalized_targets


def validate_csv_filename(filename: str) -> str:
    name = filename.strip()
    if not name:
        raise ValueError("CSV filename must not be empty")
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("CSV filename must be a filename, not a path")
    if not name.lower().endswith(".csv"):
        raise ValueError("CSV filename must end with .csv")
    return name


def resolve_csv_path(directory: str | Path, filename: str) -> Path:
    validated_name = validate_csv_filename(filename)
    return Path(directory).expanduser().resolve() / validated_name


class TrajectoryRecorder:
    """Stream samples to a partial file and publish only a valid finished CSV."""

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path).expanduser().resolve()
        validate_csv_filename(self.output_path.name)
        self.partial_path = self.output_path.with_name(
            f"{self.output_path.stem}.partial{self.output_path.suffix}"
        )
        self._stream: IO[str] | None = None
        self._writer: csv.DictWriter | None = None
        self._last_time = -1.0
        self._sample_count = 0

    @property
    def active(self) -> bool:
        return self._stream is not None

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def start(self, initial_targets: Mapping[str, float]) -> None:
        if self.active:
            raise RuntimeError("Recorder is already active")
        if self.output_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing CSV: {self.output_path}")
        if self.partial_path.exists():
            raise FileExistsError(
                f"Partial recording already exists; inspect or remove it first: {self.partial_path}"
            )

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.partial_path.open(
            "x", encoding="utf-8", newline="", buffering=1
        )
        self._writer = csv.DictWriter(self._stream, fieldnames=list(CSV_COLUMNS))
        self._writer.writeheader()
        self._last_time = -1.0
        self._sample_count = 0
        self.record_sample(0.0, initial_targets)

    def record_sample(
        self, relative_time: float, targets: Mapping[str, float]
    ) -> None:
        if not self.active or self._writer is None:
            raise RuntimeError("Recorder has not been started")
        time_value = float(relative_time)
        if not math.isfinite(time_value) or time_value < 0:
            raise ValueError("Recording time must be finite and non-negative")
        if time_value <= self._last_time:
            raise ValueError("Recording times must be strictly increasing")

        values = normalized_targets(targets)
        row: dict[str, str] = {"time": f"{time_value:.9f}"}
        row.update({name: f"{values[name]:.9f}" for name in JOINT_NAMES})
        self._writer.writerow(row)
        self._last_time = time_value
        self._sample_count += 1

    def stop(self) -> Path:
        if not self.active or self._stream is None:
            raise RuntimeError("Recorder has not been started")

        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        self._stream = None
        self._writer = None

        if self._sample_count < 2:
            raise ValueError(
                f"Recording needs at least two samples; partial file kept at {self.partial_path}"
            )
        JointTrajectory.from_csv(self.partial_path)
        if self.output_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing CSV: {self.output_path}")
        os.replace(self.partial_path, self.output_path)
        return self.output_path

    def abort(self) -> Path | None:
        """Close without publishing; keep the partial file for diagnosis/recovery."""

        if self._stream is not None:
            self._stream.flush()
            self._stream.close()
            self._stream = None
            self._writer = None
        return self.partial_path if self.partial_path.exists() else None

