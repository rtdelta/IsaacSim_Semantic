from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .atomic_io import commit_staging, create_staging_directory, write_json
from .config import RunConfig, resolved_config_dict
from .file_index import build_file_index
from .identity_resolver import AnnotationIdentityResolver, create_identity_resolver
from .models import (
    FileIndex,
    FrameResult,
    GroupDecision,
    RatioMatrix,
    RuleMasks,
    ToothDecision,
)
from .output_writer import OutputWriter
from .preflight import run_preflight
from .ratio_reader import load_ratio_matrix
from .reporter import build_summary, write_reports
from .rules import build_rule_masks
from .yolo_reader import format_preserved_lines, parse_yolo_file


PIPELINE_VERSION = "1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _optional_ratio(value: float) -> Optional[float]:
    return float(value) if np.isfinite(value) else None


def _ratio_reason(status: str, dropped: bool, threshold: float) -> str:
    if status == "reference_missing":
        return "reference_missing policy applied"
    if status == "empty_ratio":
        return "empty_ratio policy applied"
    if dropped:
        return f"pixel_ratio is below {threshold:.12g}"
    return f"pixel_ratio is at or above {threshold:.12g}"


def _process_frame(
    ordinal: int,
    config: RunConfig,
    ratios: RatioMatrix,
    masks: RuleMasks,
    file_index: FileIndex,
    resolver: AnnotationIdentityResolver,
    writer: OutputWriter,
) -> FrameResult:
    frame_id = ratios.frame_ids[ordinal]
    tooth_label_path = file_index.tooth.labels[frame_id]
    tooth_annotations = parse_yolo_file(
        tooth_label_path,
        maximum_annotations=5,
    )
    resolved = resolver.resolve(
        tooth_annotations,
        masks.legacy_eligible[ordinal],
    )
    resolved_by_label = {item.semantic_label: item for item in resolved}
    quarantined = bool(masks.quarantine_frames[ordinal])
    threshold = config.rules.single_tooth.minimum_visible_ratio
    tooth_decisions = []
    anomalies: List[Mapping[str, object]] = []

    for target_index, label in enumerate(ratios.labels):
        item = resolved_by_label.get(label)
        source_present = item is not None
        status = str(ratios.statuses[ordinal, target_index])
        ratio_value = _optional_ratio(ratios.ratios[ordinal, target_index])
        dropped = bool(masks.single_drop[ordinal, target_index])
        if source_present:
            if quarantined:
                action = "quarantine"
                reason = "frame contains a quarantined ratio"
            elif dropped:
                action = "drop"
                reason = _ratio_reason(status, True, threshold)
            else:
                action = "keep"
                reason = _ratio_reason(status, False, threshold)
        else:
            action = "source_absent"
            reason = "upstream single-tooth annotation is absent"

        tooth_decisions.append(
            ToothDecision(
                frame_id=frame_id,
                semantic_label=label,
                target_index=target_index,
                source_present=source_present,
                source_class_id=(
                    item.annotation.class_id if item is not None else None
                ),
                source_line_number=(
                    item.annotation.line_number if item is not None else None
                ),
                whole_pixels=int(ratios.whole_counts[ordinal, target_index]),
                reference_pixels=int(
                    ratios.reference_counts[ordinal, target_index]
                ),
                ratio=ratio_value,
                ratio_status=status,
                threshold=threshold,
                action=action,
                reason=reason,
            )
        )
        if status != "valid":
            anomalies.append(
                {
                    "frame_id": frame_id,
                    "semantic_label": label,
                    "type": status,
                    "whole_pixels": int(
                        ratios.whole_counts[ordinal, target_index]
                    ),
                    "reference_pixels": int(
                        ratios.reference_counts[ordinal, target_index]
                    ),
                    "pixel_ratio": "" if ratio_value is None else ratio_value,
                    "message": reason,
                }
            )

    kept_annotations = [
        item.annotation
        for item in resolved
        if not bool(masks.single_drop[ordinal, item.target_index])
    ]
    tooth_output_text = (
        None
        if quarantined
        else format_preserved_lines(tuple(kept_annotations))
    )
    group_label_path = file_index.group.labels.get(frame_id)
    group_annotations = (
        parse_yolo_file(group_label_path, maximum_annotations=1)
        if group_label_path is not None
        else ()
    )
    group_source_present = bool(group_annotations)
    group_dropped = bool(masks.group_drop[ordinal])
    if quarantined:
        group_action = "quarantine" if group_source_present else "source_absent"
        group_reason = (
            "frame contains a quarantined ratio"
            if group_source_present
            else "upstream group annotation is absent"
        )
        group_output_text = None
    elif not group_source_present:
        group_action = "source_absent"
        group_reason = "upstream group annotation is absent"
        group_output_text = "" if group_label_path is not None else None
    elif group_dropped:
        group_action = "drop"
        group_reason = (
            f"{int(masks.group_low_counts[ordinal])} teeth are below "
            f"{config.rules.tooth_group.minimum_visible_ratio:.12g}"
        )
        group_output_text = ""
    else:
        group_action = "keep"
        group_reason = (
            f"{int(masks.group_low_counts[ordinal])} teeth are below "
            f"{config.rules.tooth_group.minimum_visible_ratio:.12g}"
        )
        group_output_text = format_preserved_lines(group_annotations)

    result = FrameResult(
        ordinal=ordinal,
        frame_id=frame_id,
        tooth_decisions=tuple(tooth_decisions),
        group_decision=GroupDecision(
            frame_id=frame_id,
            ratios=tuple(
                _optional_ratio(value) for value in ratios.ratios[ordinal]
            ),
            statuses=tuple(
                str(value) for value in ratios.statuses[ordinal].tolist()
            ),
            threshold=config.rules.tooth_group.minimum_visible_ratio,
            low_count=int(masks.group_low_counts[ordinal]),
            minimum_low_teeth=config.rules.tooth_group.minimum_low_teeth,
            source_present=group_source_present,
            action=group_action,
            reason=group_reason,
        ),
        tooth_source_boxes=len(tooth_annotations),
        tooth_kept_boxes=len(kept_annotations) if not quarantined else 0,
        tooth_dropped_boxes=sum(
            decision.action == "drop" for decision in tooth_decisions
        ),
        group_source_boxes=len(group_annotations),
        group_kept_boxes=1 if group_action == "keep" else 0,
        group_dropped_boxes=1 if group_action == "drop" else 0,
        tooth_output_text=tooth_output_text,
        group_output_text=group_output_text,
        tooth_label_name=tooth_label_path.name,
        group_label_name=(
            group_label_path.name if group_label_path is not None else None
        ),
        anomalies=tuple(anomalies),
    )
    writer.write_frame(result)
    return result


def _execute_frames(
    config: RunConfig,
    ratios: RatioMatrix,
    masks: RuleMasks,
    file_index: FileIndex,
    resolver: AnnotationIdentityResolver,
    writer: OutputWriter,
) -> Tuple[FrameResult, ...]:
    frame_count = len(ratios.frame_ids)
    if config.execution.workers == 1:
        return tuple(
            _process_frame(
                ordinal,
                config,
                ratios,
                masks,
                file_index,
                resolver,
                writer,
            )
            for ordinal in range(frame_count)
        )

    results: List[FrameResult] = []
    errors: List[Tuple[int, BaseException]] = []
    with ThreadPoolExecutor(max_workers=config.execution.workers) as executor:
        pending: Dict[Future, int] = {}
        next_ordinal = 0

        def submit_until_full() -> None:
            nonlocal next_ordinal
            while (
                next_ordinal < frame_count
                and len(pending) < config.execution.max_in_flight
            ):
                ordinal = next_ordinal
                next_ordinal += 1
                future = executor.submit(
                    _process_frame,
                    ordinal,
                    config,
                    ratios,
                    masks,
                    file_index,
                    resolver,
                    writer,
                )
                pending[future] = ordinal

        submit_until_full()
        stop_submitting = False
        while pending:
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in done:
                ordinal = pending.pop(future)
                try:
                    results.append(future.result())
                except BaseException as exc:
                    errors.append((ordinal, exc))
                    if config.execution.on_error == "fail_fast":
                        stop_submitting = True
            if stop_submitting:
                for future in pending:
                    future.cancel()
                break
            submit_until_full()

    if errors:
        errors.sort(key=lambda item: item[0])
        ordinal, exc = errors[0]
        frame_id = ratios.frame_ids[ordinal]
        raise RuntimeError(
            f"frame {frame_id} failed: {type(exc).__name__}: {exc}"
        ) from exc
    if len(results) != frame_count:
        raise RuntimeError(
            f"pipeline completed {len(results)} of {frame_count} frames"
        )
    return tuple(sorted(results, key=lambda item: item.ordinal))


def _initial_manifest(
    config: RunConfig,
    input_fingerprint: str,
    config_fingerprint: str,
    ratio_backend: str,
    frame_count: int,
) -> Dict[str, object]:
    return {
        "schema_version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "status": "running",
        "started_at": _utc_now(),
        "config_path": str(config.config_path),
        "config_fingerprint": config_fingerprint,
        "input_fingerprint": input_fingerprint,
        "identity_mode": config.identity.mode,
        "ratio_backend": ratio_backend,
        "frames": frame_count,
        "inputs": {
            "postprocess_output_root": str(
                config.inputs.postprocess.output_root
            ),
            "pixel_ratio_output_root": str(
                config.inputs.pixel_ratio.output_root
            ),
        },
        "resolved_config": resolved_config_dict(config),
    }


def run_pipeline(config: RunConfig) -> Mapping[str, object]:
    started = time.perf_counter()
    timings: Dict[str, float] = {}

    phase = time.perf_counter()
    contract = run_preflight(config)
    timings["preflight"] = time.perf_counter() - phase

    phase = time.perf_counter()
    ratios = load_ratio_matrix(config, contract)
    timings["ratio_load"] = time.perf_counter() - phase

    phase = time.perf_counter()
    masks = build_rule_masks(config, ratios)
    timings["rule_build"] = time.perf_counter() - phase

    phase = time.perf_counter()
    file_index = build_file_index(config, ratios)
    timings["file_index"] = time.perf_counter() - phase

    staging_root = create_staging_directory(config.output.root)
    manifest = _initial_manifest(
        config,
        contract.input_fingerprint,
        contract.config_fingerprint,
        ratios.source_backend,
        len(ratios.frame_ids),
    )
    write_json(staging_root / "manifest.json", manifest)
    writer = OutputWriter(config, staging_root, file_index)
    resolver = create_identity_resolver(config)

    try:
        writer.prepare()
        phase = time.perf_counter()
        results = _execute_frames(
            config,
            ratios,
            masks,
            file_index,
            resolver,
            writer,
        )
        timings["frame_processing"] = time.perf_counter() - phase

        phase = time.perf_counter()
        verified_frames = writer.verify(results)
        timings["verification"] = time.perf_counter() - phase

        timings["total"] = time.perf_counter() - started
        summary = build_summary(
            config,
            ratios,
            results,
            timings,
            verified_frames,
        )
        phase = time.perf_counter()
        write_reports(staging_root, config, results, summary)
        timings["reporting"] = time.perf_counter() - phase
        timings["total"] = time.perf_counter() - started
        summary = build_summary(
            config,
            ratios,
            results,
            timings,
            verified_frames,
        )
        write_json(staging_root / "summary.json", summary)

        manifest["status"] = "completed"
        manifest["finished_at"] = _utc_now()
        manifest["summary"] = summary
        write_json(staging_root / "manifest.json", manifest)
        phase = time.perf_counter()
        commit_staging(
            staging_root,
            config.output.root,
            config.output.overwrite,
        )
        timings["commit"] = time.perf_counter() - phase
        return summary
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["finished_at"] = _utc_now()
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        try:
            write_json(staging_root / "manifest.json", manifest)
        except OSError:
            pass
        raise
