from __future__ import annotations

import csv
import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np

from .config import RunConfig
from .models import InputContract, RatioMatrix


def _frame_sort_key(frame_id: str) -> Tuple[int, object]:
    if frame_id.isdigit():
        return (0, int(frame_id))
    return (1, frame_id)


def _finalize_matrix(
    frame_ids: Tuple[str, ...],
    labels: Tuple[str, ...],
    whole_counts: np.ndarray,
    reference_counts: np.ndarray,
    statuses: np.ndarray,
    backend: str,
    ratio_over_one: str,
) -> RatioMatrix:
    expected = (len(frame_ids), len(labels))
    if whole_counts.shape != expected or reference_counts.shape != expected:
        raise ValueError(
            "ratio count arrays must have shape "
            f"{expected}; whole={whole_counts.shape}, "
            f"reference={reference_counts.shape}"
        )
    if not np.issubdtype(whole_counts.dtype, np.integer):
        raise ValueError("whole_counts must use an integer dtype")
    if not np.issubdtype(reference_counts.dtype, np.integer):
        raise ValueError("reference_counts must use an integer dtype")
    if np.any(whole_counts < 0) or np.any(reference_counts < 0):
        raise ValueError("ratio counts must be non-negative")

    whole = whole_counts.astype(np.uint64, copy=False)
    reference = reference_counts.astype(np.uint64, copy=False)
    valid = reference > 0
    ratios = np.full(expected, np.nan, dtype=np.float64)
    np.divide(whole, reference, out=ratios, where=valid)

    computed_statuses = np.full(expected, "valid", dtype="<U20")
    computed_statuses[~valid] = "reference_missing"
    over_one = valid & (ratios > 1.0)
    computed_statuses[over_one] = "ratio_over_one"
    if statuses.shape != expected:
        raise ValueError(f"statuses must have shape {expected}")
    # CSV can explicitly identify an empty ratio with a nonzero denominator.
    empty = statuses == "empty_ratio"
    computed_statuses[empty] = "empty_ratio"
    ratios[empty] = np.nan

    if ratio_over_one == "error" and np.any(over_one):
        first = np.argwhere(over_one)[0]
        raise ValueError(
            "ratio_over_one encountered at "
            f"frame={frame_ids[int(first[0])]}, label={labels[int(first[1])]}"
        )
    if ratio_over_one == "clip":
        np.minimum(ratios, 1.0, out=ratios, where=np.isfinite(ratios))

    return RatioMatrix(
        frame_ids=frame_ids,
        labels=labels,
        whole_counts=whole,
        reference_counts=reference,
        ratios=ratios,
        statuses=computed_statuses,
        source_backend=backend,
    )


class RatioReader(ABC):
    @abstractmethod
    def load(
        self,
        config: RunConfig,
        contract: InputContract,
    ) -> RatioMatrix:
        raise NotImplementedError


class NpzRatioReader(RatioReader):
    def load(
        self,
        config: RunConfig,
        contract: InputContract,
    ) -> RatioMatrix:
        path = config.inputs.pixel_ratio.counts_cache
        try:
            archive = np.load(path, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot load counts cache {path}: {exc}") from exc
        try:
            required = {"frame_ids", "whole_counts", "reference_counts"}
            missing = sorted(required - set(archive.files))
            if missing:
                raise ValueError(
                    "counts cache is missing arrays: " + ", ".join(missing)
                )
            frame_array = np.asarray(archive["frame_ids"])
            if frame_array.ndim != 1:
                raise ValueError("counts cache frame_ids must be one-dimensional")
            frame_ids = tuple(str(value) for value in frame_array.tolist())
            if not frame_ids:
                raise ValueError("counts cache contains no frame IDs")
            if len(set(frame_ids)) != len(frame_ids):
                raise ValueError("counts cache contains duplicate frame IDs")
            if "ordinals" in archive.files:
                expected_ordinals = np.arange(len(frame_ids), dtype=np.int64)
                ordinals = np.asarray(archive["ordinals"], dtype=np.int64)
                if not np.array_equal(ordinals, expected_ordinals):
                    raise ValueError(
                        "counts cache ordinals are incomplete or unordered"
                    )
            whole = np.asarray(archive["whole_counts"])
            reference = np.asarray(archive["reference_counts"])
        finally:
            archive.close()

        statuses = np.full(whole.shape, "valid", dtype="<U20")
        return _finalize_matrix(
            frame_ids=frame_ids,
            labels=config.targets.labels_in_physical_order,
            whole_counts=whole,
            reference_counts=reference,
            statuses=statuses,
            backend="counts_cache_npz",
            ratio_over_one=config.ratio_handling.ratio_over_one,
        )


class CsvRatioReader(RatioReader):
    REQUIRED_FIELDS = {
        "frame_id",
        "target",
        "whole_pixels",
        "reference_pixels",
        "pixel_ratio",
        "status",
    }

    def load(
        self,
        config: RunConfig,
        contract: InputContract,
    ) -> RatioMatrix:
        del contract
        path = config.inputs.pixel_ratio.per_frame_csv
        records: Dict[Tuple[str, str], Tuple[int, int, str, str]] = {}
        seen_frames = set()
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError("ratio CSV has no header")
                missing = sorted(self.REQUIRED_FIELDS - set(reader.fieldnames))
                if missing:
                    raise ValueError(
                        "ratio CSV is missing fields: " + ", ".join(missing)
                    )
                for row_number, row in enumerate(reader, start=2):
                    frame_id = (row.get("frame_id") or "").strip()
                    target = (row.get("target") or "").strip()
                    if not frame_id or not target:
                        raise ValueError(
                            f"ratio CSV row {row_number} has an empty key"
                        )
                    seen_frames.add(frame_id)
                    if target == config.targets.group_name:
                        continue
                    if target not in config.targets.labels_in_physical_order:
                        raise ValueError(
                            f"ratio CSV row {row_number} has unknown target {target!r}"
                        )
                    key = (frame_id, target)
                    if key in records:
                        raise ValueError(
                            f"ratio CSV contains duplicate row for {key}"
                        )
                    try:
                        whole = int((row.get("whole_pixels") or "").strip())
                        reference = int(
                            (row.get("reference_pixels") or "").strip()
                        )
                    except ValueError as exc:
                        raise ValueError(
                            f"ratio CSV row {row_number} has invalid counts"
                        ) from exc
                    if whole < 0 or reference < 0:
                        raise ValueError(
                            f"ratio CSV row {row_number} has negative counts"
                        )
                    ratio_text = (row.get("pixel_ratio") or "").strip()
                    status = (row.get("status") or "").strip()
                    if status not in {
                        "valid",
                        "ratio_over_one",
                        "reference_missing",
                    }:
                        raise ValueError(
                            f"ratio CSV row {row_number} has unsupported status "
                            f"{status!r}"
                        )
                    records[key] = (whole, reference, ratio_text, status)
        except OSError as exc:
            raise ValueError(f"cannot read ratio CSV {path}: {exc}") from exc

        frame_ids = tuple(sorted(seen_frames, key=_frame_sort_key))
        labels = config.targets.labels_in_physical_order
        shape = (len(frame_ids), len(labels))
        whole_counts = np.zeros(shape, dtype=np.uint64)
        reference_counts = np.zeros(shape, dtype=np.uint64)
        statuses = np.full(shape, "valid", dtype="<U20")
        for frame_index, frame_id in enumerate(frame_ids):
            for target_index, label in enumerate(labels):
                key = (frame_id, label)
                if key not in records:
                    raise ValueError(f"ratio CSV is missing row for {key}")
                whole, reference, ratio_text, source_status = records[key]
                whole_counts[frame_index, target_index] = whole
                reference_counts[frame_index, target_index] = reference
                if not ratio_text and reference > 0:
                    statuses[frame_index, target_index] = "empty_ratio"
                elif ratio_text:
                    try:
                        reported_ratio = float(ratio_text)
                    except ValueError as exc:
                        raise ValueError(
                            f"ratio CSV contains invalid ratio for {key}"
                        ) from exc
                    if not math.isfinite(reported_ratio):
                        raise ValueError(
                            f"ratio CSV contains non-finite ratio for {key}"
                        )
                    expected = whole / reference if reference else None
                    if expected is None:
                        raise ValueError(
                            f"ratio CSV reports a ratio with zero reference for {key}"
                        )
                    if not math.isclose(
                        reported_ratio,
                        expected,
                        rel_tol=1e-9,
                        abs_tol=1e-12,
                    ):
                        raise ValueError(
                            f"ratio CSV ratio does not match counts for {key}"
                        )
                if reference == 0 and source_status != "reference_missing":
                    raise ValueError(
                        f"ratio CSV status must be reference_missing for {key}"
                    )
                if reference == 0 and ratio_text:
                    raise ValueError(
                        f"ratio CSV must leave pixel_ratio empty for {key}"
                    )
                if reference > 0 and ratio_text:
                    expected_status = (
                        "ratio_over_one"
                        if whole / reference > 1.0
                        else "valid"
                    )
                    if source_status != expected_status:
                        raise ValueError(
                            f"ratio CSV status does not match counts for {key}; "
                            f"expected {expected_status!r}, got {source_status!r}"
                        )

        return _finalize_matrix(
            frame_ids=frame_ids,
            labels=labels,
            whole_counts=whole_counts,
            reference_counts=reference_counts,
            statuses=statuses,
            backend="per_frame_csv",
            ratio_over_one=config.ratio_handling.ratio_over_one,
        )


def create_ratio_reader(config: RunConfig) -> RatioReader:
    if config.inputs.pixel_ratio.input_format == "counts_cache_npz":
        return NpzRatioReader()
    if config.inputs.pixel_ratio.input_format == "per_frame_csv":
        return CsvRatioReader()
    raise ValueError(
        "unsupported ratio input format: "
        f"{config.inputs.pixel_ratio.input_format}"
    )


def load_ratio_matrix(
    config: RunConfig,
    contract: InputContract,
) -> RatioMatrix:
    return create_ratio_reader(config).load(config, contract)
