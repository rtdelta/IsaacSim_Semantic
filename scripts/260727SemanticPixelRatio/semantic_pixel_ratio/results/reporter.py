from __future__ import annotations

import math
import os
import statistics
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from ..config import RatioConfig, TargetsConfig
from ..models import CountLedgerData, TargetRow
from .atomic_io import atomic_write_csv, atomic_write_json


def _ratio(whole: int, reference: int) -> Tuple[float | None, str]:
    if reference == 0:
        return None, "reference_missing"
    value = whole / reference
    return value, "ratio_over_one" if value > 1.0 else "valid"


def build_rows(
    ledger: CountLedgerData,
    targets: TargetsConfig,
    pixels_per_frame: int,
) -> List[TargetRow]:
    return list(_iter_rows(ledger, targets, pixels_per_frame))


def _validate_ledger(
    ledger: CountLedgerData,
    pixels_per_frame: int,
) -> None:
    expected_ordinals = np.arange(len(ledger.frame_ids), dtype=np.int64)
    if not np.array_equal(ledger.ordinals, expected_ordinals):
        raise ValueError("ledger ordinals are incomplete, duplicated, or unordered")
    if len(set(ledger.frame_ids)) != len(ledger.frame_ids):
        raise ValueError("ledger contains duplicate frame IDs")
    if np.any(ledger.whole_counts > pixels_per_frame):
        raise ValueError("whole-scene pixel count exceeds frame pixel count")
    if np.any(ledger.reference_counts > pixels_per_frame):
        raise ValueError("reference pixel count exceeds frame pixel count")


def _iter_rows(
    ledger: CountLedgerData,
    targets: TargetsConfig,
    pixels_per_frame: int,
) -> Iterable[TargetRow]:
    _validate_ledger(ledger, pixels_per_frame)
    all_targets = (*targets.labels, targets.group_name)
    for index, frame_id in enumerate(ledger.frame_ids):
        whole_values = [
            int(value) for value in ledger.whole_counts[index].tolist()
        ]
        reference_values = [
            int(value) for value in ledger.reference_counts[index].tolist()
        ]
        whole_values.append(sum(whole_values))
        reference_values.append(sum(reference_values))
        if whole_values[-1] > pixels_per_frame:
            raise ValueError(
                f"group whole-scene count exceeds frame pixels: {frame_id}"
            )
        if reference_values[-1] > pixels_per_frame:
            raise ValueError(
                f"group reference count exceeds frame pixels: {frame_id}"
            )
        for target, whole, reference in zip(
            all_targets,
            whole_values,
            reference_values,
        ):
            ratio, status = _ratio(whole, reference)
            yield TargetRow(
                frame_id=frame_id,
                target=target,
                whole_pixels=whole,
                reference_pixels=reference,
                ratio=ratio,
                status=status,
            )


def _format_ratio(value: float | None) -> str:
    return "" if value is None else format(value, ".12g")


def _csv_rows(rows: Iterable[TargetRow]) -> Iterable[Dict[str, object]]:
    for row in rows:
        yield {
            "frame_id": row.frame_id,
            "target": row.target,
            "whole_pixels": row.whole_pixels,
            "reference_pixels": row.reference_pixels,
            "pixel_ratio": _format_ratio(row.ratio),
            "status": row.status,
        }


def _target_summary(
    target: str,
    rows: Sequence[TargetRow],
) -> Dict[str, object]:
    whole_total = sum(row.whole_pixels for row in rows)
    reference_total = sum(row.reference_pixels for row in rows)
    valid_ratios = [row.ratio for row in rows if row.ratio is not None]
    return {
        "target": target,
        "frames": len(rows),
        "whole_pixels_total": whole_total,
        "reference_pixels_total": reference_total,
        "aggregate_ratio": (
            whole_total / reference_total if reference_total else None
        ),
        "valid_frame_count": len(valid_ratios),
        "zero_reference_frame_count": sum(
            row.status == "reference_missing" for row in rows
        ),
        "ratio_over_one_frame_count": sum(
            row.status == "ratio_over_one" for row in rows
        ),
        "mean_frame_ratio": (
            math.fsum(valid_ratios) / len(valid_ratios)
            if valid_ratios
            else None
        ),
        "median_frame_ratio": (
            statistics.median(valid_ratios) if valid_ratios else None
        ),
        "min_frame_ratio": min(valid_ratios) if valid_ratios else None,
        "max_frame_ratio": max(valid_ratios) if valid_ratios else None,
    }


def build_summary(
    rows: Sequence[TargetRow],
    target_names: Sequence[str],
    backend_name: str,
    elapsed_seconds: float,
) -> Dict[str, object]:
    grouped = {
        target: [row for row in rows if row.target == target]
        for target in target_names
    }
    frames = len(grouped[target_names[0]]) if target_names else 0
    return {
        "schema_version": 1,
        "status": "completed",
        "backend": backend_name,
        "frames": frames,
        "target_rows": len(rows),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "frames_per_second": (
            round(frames / elapsed_seconds, 6) if elapsed_seconds else 0.0
        ),
        "targets": [
            _target_summary(target, grouped[target])
            for target in target_names
        ],
    }


def write_counts_cache(path: Path, ledger: CountLedgerData) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez(
                handle,
                ordinals=ledger.ordinals,
                frame_ids=np.asarray(ledger.frame_ids, dtype=np.str_),
                whole_counts=ledger.whole_counts,
                reference_counts=ledger.reference_counts,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_reports(
    output_root: Path,
    ledger: CountLedgerData,
    targets: TargetsConfig,
    ratio_config: RatioConfig,
    pixels_per_frame: int,
    backend_name: str,
    elapsed_seconds: float,
    write_cache: bool,
) -> Dict[str, object]:
    del ratio_config
    target_names = (*targets.labels, targets.group_name)
    _validate_ledger(ledger, pixels_per_frame)
    summary_items = []
    for target_index, target in enumerate(target_names):
        if target_index < 5:
            whole_values = ledger.whole_counts[:, target_index].astype(
                np.uint64,
                copy=False,
            )
            reference_values = ledger.reference_counts[:, target_index].astype(
                np.uint64,
                copy=False,
            )
        else:
            whole_values = ledger.whole_counts.sum(axis=1, dtype=np.uint64)
            reference_values = ledger.reference_counts.sum(
                axis=1,
                dtype=np.uint64,
            )
        target_rows = []
        for frame_index, frame_id in enumerate(ledger.frame_ids):
            whole = int(whole_values[frame_index])
            reference = int(reference_values[frame_index])
            ratio, status = _ratio(whole, reference)
            target_rows.append(
                TargetRow(
                    frame_id=frame_id,
                    target=target,
                    whole_pixels=whole,
                    reference_pixels=reference,
                    ratio=ratio,
                    status=status,
                )
            )
        summary_items.append(_target_summary(target, target_rows))
    frames = len(ledger.frame_ids)
    summary = {
        "schema_version": 1,
        "status": "completed",
        "backend": backend_name,
        "frames": frames,
        "target_rows": frames * len(target_names),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "frames_per_second": (
            round(frames / elapsed_seconds, 6) if elapsed_seconds else 0.0
        ),
        "targets": summary_items,
    }
    fields = (
        "frame_id",
        "target",
        "whole_pixels",
        "reference_pixels",
        "pixel_ratio",
        "status",
    )
    atomic_write_csv(
        output_root / "per_frame.csv",
        fields,
        _csv_rows(_iter_rows(ledger, targets, pixels_per_frame)),
    )
    atomic_write_csv(
        output_root / "anomalies.csv",
        fields,
        _csv_rows(
            row
            for row in _iter_rows(ledger, targets, pixels_per_frame)
            if row.status != "valid"
        ),
    )
    summary_rows = []
    for item in summary["targets"]:
        summary_rows.append(
            {
                key: _format_ratio(value)
                if key.endswith("_ratio")
                else value
                for key, value in item.items()
            }
        )
    atomic_write_csv(
        output_root / "summary.csv",
        tuple(summary_rows[0].keys()) if summary_rows else ("target",),
        summary_rows,
    )
    atomic_write_json(output_root / "summary.json", summary)
    if write_cache:
        write_counts_cache(output_root / "counts_cache.npz", ledger)
    return summary
