"""Crash-safe CSV recording of articulation joints and optional root state."""

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
    """Write joint angles and optional numeric fields with crash-safe publication."""

    def __init__(
        self,
        output_path: str | Path,
        joint_names: Sequence[str],
        additional_columns: Sequence[str] = (),
    ) -> None:
        self.output_path = Path(output_path).expanduser().resolve()
        self.joint_names = tuple(str(name) for name in joint_names)
        if not self.joint_names or len(set(self.joint_names)) != len(self.joint_names):
            raise RecorderError("joint_names must be a non-empty unique sequence")
        self.additional_columns = tuple(str(name).strip() for name in additional_columns)
        all_columns = ("time", *self.joint_names, *self.additional_columns)
        if any(not name for name in self.additional_columns):
            raise RecorderError("additional_columns cannot contain an empty name")
        if len(set(all_columns)) != len(all_columns):
            raise RecorderError("CSV column names must be unique")
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
        initial_additional_values: Sequence[float] = (),
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
        self._writer.writerow(("time", *self.joint_names, *self.additional_columns))
        self._metadata = dict(metadata or {})
        self._last_time = None
        self._sample_count = 0
        self.record(0.0, initial_positions_degrees, initial_additional_values)

    def record(
        self,
        elapsed_seconds: float,
        positions_degrees: Sequence[float],
        additional_values: Sequence[float] = (),
    ) -> None:
        if not self.active or self._writer is None:
            raise RecorderError("Recorder is not active")
        timestamp = float(elapsed_seconds)
        positions = tuple(float(value) for value in positions_degrees)
        additional = tuple(float(value) for value in additional_values)
        if len(positions) != len(self.joint_names):
            raise RecorderError(
                f"Expected {len(self.joint_names)} positions, got {len(positions)}"
            )
        if len(additional) != len(self.additional_columns):
            raise RecorderError(
                f"Expected {len(self.additional_columns)} additional values, "
                f"got {len(additional)}"
            )
        if not math.isfinite(timestamp) or timestamp < 0:
            raise RecorderError("Sample time must be finite and non-negative")
        if any(not math.isfinite(value) for value in positions):
            raise RecorderError("Joint positions must all be finite")
        if any(not math.isfinite(value) for value in additional):
            raise RecorderError("Additional sample values must all be finite")
        if self._last_time is not None and timestamp <= self._last_time:
            raise RecorderError("Sample times must be strictly increasing")
        self._writer.writerow(
            (
                f"{timestamp:.9f}",
                *(f"{value:.9f}" for value in positions),
                *(f"{value:.9f}" for value in additional),
            )
        )
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
        published_metadata.setdefault(
            "column_descriptions",
            self._default_column_descriptions(),
        )
        published_metadata.setdefault(
            "column_descriptions_note",
            "CSV first row is the machine-readable header; meanings and units for "
            "every column are documented in column_descriptions in this metadata file.",
        )
        published_metadata.update(
            {
                "csv": str(self.output_path),
                "joint_order": list(self.joint_names),
                "additional_columns": list(self.additional_columns),
                "csv_columns": ["time", *self.joint_names, *self.additional_columns],
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

    def _default_column_descriptions(self) -> dict[str, str]:
        """Provide a fallback meaning for every CSV field.

        The excavator controller supplies more precise Chinese descriptions for
        Root pose fields; this fallback keeps the recorder self-describing when
        used independently.
        """

        descriptions = {
            "time": "Sample time accumulated from recording start; unit: second (s)",
        }
        descriptions.update(
            {
                name: "Actual joint value; unit and joint mapping are defined by the caller"
                for name in self.joint_names
            }
        )
        descriptions.update(
            {
                name: "Additional numeric sample field; meaning is defined by the caller"
                for name in self.additional_columns
            }
        )
        return descriptions

    def abort(self) -> Path | None:
        """Close the stream while intentionally retaining any partial CSV."""

        if self._stream is not None:
            self._stream.flush()
            self._stream.close()
            self._stream = None
            self._writer = None
        return self.partial_path if self.partial_path.exists() else None
