from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from .atomic_io import write_csv, write_json
from .config import RunConfig
from .models import FrameResult, RatioMatrix


DECISION_FIELDS = (
    "frame_id",
    "semantic_label",
    "target_index",
    "source_present",
    "source_class_id",
    "source_line_number",
    "whole_pixels",
    "reference_pixels",
    "pixel_ratio",
    "ratio_status",
    "threshold",
    "action",
    "reason",
)

FRAME_FIELDS = (
    "frame_id",
    "tooth_1_ratio",
    "tooth_2_ratio",
    "tooth_3_ratio",
    "tooth_4_ratio",
    "tooth_5_ratio",
    "tooth_1_status",
    "tooth_2_status",
    "tooth_3_status",
    "tooth_4_status",
    "tooth_5_status",
    "group_threshold",
    "low_count",
    "minimum_low_teeth",
    "source_group_present",
    "group_action",
    "reason",
)

ANOMALY_FIELDS = (
    "frame_id",
    "semantic_label",
    "type",
    "whole_pixels",
    "reference_pixels",
    "pixel_ratio",
    "message",
)


def _ratio_text(value: object) -> str:
    if value is None:
        return ""
    number = float(value)
    return "" if not math.isfinite(number) else format(number, ".12g")


def _decision_rows(results: Sequence[FrameResult]) -> Iterable[Mapping[str, object]]:
    for result in results:
        for decision in result.tooth_decisions:
            yield {
                "frame_id": decision.frame_id,
                "semantic_label": decision.semantic_label,
                "target_index": decision.target_index,
                "source_present": decision.source_present,
                "source_class_id": (
                    "" if decision.source_class_id is None else decision.source_class_id
                ),
                "source_line_number": (
                    ""
                    if decision.source_line_number is None
                    else decision.source_line_number
                ),
                "whole_pixels": decision.whole_pixels,
                "reference_pixels": decision.reference_pixels,
                "pixel_ratio": _ratio_text(decision.ratio),
                "ratio_status": decision.ratio_status,
                "threshold": format(decision.threshold, ".12g"),
                "action": decision.action,
                "reason": decision.reason,
            }


def _frame_rows(results: Sequence[FrameResult]) -> Iterable[Mapping[str, object]]:
    for result in results:
        decision = result.group_decision
        row: Dict[str, object] = {
            "frame_id": result.frame_id,
            "group_threshold": format(decision.threshold, ".12g"),
            "low_count": decision.low_count,
            "minimum_low_teeth": decision.minimum_low_teeth,
            "source_group_present": decision.source_present,
            "group_action": decision.action,
            "reason": decision.reason,
        }
        for index, ratio in enumerate(decision.ratios, start=1):
            row[f"tooth_{index}_ratio"] = _ratio_text(ratio)
        for index, status in enumerate(decision.statuses, start=1):
            row[f"tooth_{index}_status"] = status
        yield row


def _anomaly_rows(results: Sequence[FrameResult]) -> Iterable[Mapping[str, object]]:
    for result in results:
        yield from result.anomalies


def build_summary(
    config: RunConfig,
    ratios: RatioMatrix,
    results: Sequence[FrameResult],
    timings: Mapping[str, float],
    verified_frames: int,
) -> Dict[str, object]:
    tooth_source = sum(item.tooth_source_boxes for item in results)
    tooth_kept = sum(item.tooth_kept_boxes for item in results)
    tooth_dropped = sum(item.tooth_dropped_boxes for item in results)
    group_source = sum(item.group_source_boxes for item in results)
    group_kept = sum(item.group_kept_boxes for item in results)
    group_dropped = sum(item.group_dropped_boxes for item in results)
    tooth_stats = []
    for label in config.targets.labels_in_physical_order:
        decisions = [
            decision
            for result in results
            for decision in result.tooth_decisions
            if decision.semantic_label == label
        ]
        actions = Counter(decision.action for decision in decisions)
        tooth_stats.append(
            {
                "semantic_label": label,
                "source_boxes": sum(
                    decision.source_present for decision in decisions
                ),
                "kept": actions["keep"],
                "dropped": actions["drop"],
                "source_absent": actions["source_absent"],
                "quarantined": actions["quarantine"],
            }
        )
    ratio_status_counts = Counter(
        str(status) for status in ratios.statuses.reshape(-1).tolist()
    )
    frame_count = len(ratios.frame_ids)
    total_seconds = float(timings.get("total", 0.0))
    return {
        "schema_version": 1,
        "status": "completed",
        "frames": frame_count,
        "frames_written_or_evaluated": len(results),
        "identity_mode": config.identity.mode,
        "ratio_backend": ratios.source_backend,
        "dry_run": config.execution.dry_run,
        "thresholds": {
            "single_tooth": config.rules.single_tooth.minimum_visible_ratio,
            "tooth_group": config.rules.tooth_group.minimum_visible_ratio,
            "minimum_low_teeth": config.rules.tooth_group.minimum_low_teeth,
        },
        "tooth_boxes": {
            "source": tooth_source,
            "kept": tooth_kept,
            "dropped": tooth_dropped,
            "by_target": tooth_stats,
        },
        "group_boxes": {
            "source": group_source,
            "kept": group_kept,
            "dropped": group_dropped,
            "source_absent_frames": sum(
                not item.group_decision.source_present for item in results
            ),
        },
        "ratio_status_counts": dict(sorted(ratio_status_counts.items())),
        "anomalies": sum(len(item.anomalies) for item in results),
        "verified_frames": verified_frames,
        "workers": config.execution.workers,
        "max_in_flight": config.execution.max_in_flight,
        "timings_seconds": {
            key: round(float(value), 6) for key, value in timings.items()
        },
        "frames_per_second": (
            round(frame_count / total_seconds, 6) if total_seconds else 0.0
        ),
    }


def write_reports(
    output_root: Path,
    config: RunConfig,
    results: Sequence[FrameResult],
    summary: Mapping[str, object],
) -> None:
    write_json(output_root / "summary.json", summary)
    if config.reporting.level != "full":
        return
    write_csv(
        output_root / "decisions.csv",
        DECISION_FIELDS,
        _decision_rows(results),
    )
    write_csv(
        output_root / "frame_summary.csv",
        FRAME_FIELDS,
        _frame_rows(results),
    )
    write_csv(
        output_root / "anomalies.csv",
        ANOMALY_FIELDS,
        _anomaly_rows(results),
    )
