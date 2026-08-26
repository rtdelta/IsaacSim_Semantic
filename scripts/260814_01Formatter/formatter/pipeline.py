from __future__ import annotations

import itertools
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .concurrency import bounded_parallel_map
from .discovery import discover_dataset
from .label_transform import transform_label_file
from .manifest import config_snapshot, write_formatter_manifest, write_rename_manifest
from .materializer import collect_tree_operations, materialize_file
from .models import (
    FramePlan,
    LabelTransformResult,
    MaterializeOperation,
    MaterializeResult,
    RunConfig,
)
from .naming import build_frame_plans
from .staging import commit_staging, create_staging_directory, discard_staging
from .validator import validate_staging_dataset


_RESERVED_OUTPUT_NAMES = {
    "formatter_manifest.json",
    "rename_manifest.csv",
    "source_manifest.json",
}


def _write_class_file(path: Path, class_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(class_name + "\n", encoding="utf-8")


def _collect_preserved_operations(
    config: RunConfig, staging_root: Path
) -> Sequence[MaterializeOperation]:
    operations: list[MaterializeOperation] = []
    destinations: set[Path] = set()
    source_manifest_seen = False
    reports_seen = False

    for source in sorted(config.input_root.iterdir(), key=lambda value: value.name):
        if source.name == "dataset":
            continue
        if source.name in _RESERVED_OUTPUT_NAMES:
            raise ValueError(
                f"input contains formatter-reserved top-level name: {source}"
            )
        if source.name == "reports":
            reports_seen = True
            if not config.output.preserve_reports:
                continue
            if not source.is_dir():
                raise ValueError(f"source reports path is not a directory: {source}")
            destination = staging_root / "reports"
            category = "reports"
        elif source.name == "manifest.json":
            source_manifest_seen = True
            if not source.is_file():
                raise ValueError(f"source manifest is not a file: {source}")
            destination = staging_root / "source_manifest.json"
            category = "source_manifest"
        else:
            destination = staging_root / source.name
            category = "preserved"

        collected = collect_tree_operations(
            source_root=source,
            destination_root=destination,
            category=category,
        )
        for operation in collected:
            resolved_destination = operation.destination.resolve(strict=False)
            if resolved_destination in destinations:
                raise ValueError(
                    f"duplicate preserved output path: {operation.destination}"
                )
            destinations.add(resolved_destination)
            operations.append(operation)

    if not source_manifest_seen:
        raise ValueError(f"missing source manifest: {config.input_root / 'manifest.json'}")
    if config.output.preserve_reports and not reports_seen:
        raise ValueError(f"missing source reports directory: {config.input_root / 'reports'}")
    return operations


def _image_operations(
    plans: Sequence[FramePlan], staging_root: Path
) -> Iterable[MaterializeOperation]:
    destination_root = staging_root / "dataset" / "rgb"
    for plan in plans:
        yield MaterializeOperation(
            category="image",
            source=plan.source.rgb_path,
            destination=destination_root / plan.rgb_name,
        )


def _label_operations(
    plans: Sequence[FramePlan], staging_root: Path
) -> Iterable[tuple[str, Path, Path]]:
    dataset = staging_root / "dataset"
    for plan in plans:
        yield (
            "tooth",
            plan.source.tooth_label_path,
            dataset / "tooth_boxes" / plan.tooth_label_name,
        )
        yield (
            "collision",
            plan.source.collision_label_path,
            dataset / "tooth_collision_model" / plan.collision_label_name,
        )


def _aggregate_label_results(
    results: Iterable[LabelTransformResult],
) -> Mapping[str, Mapping[str, object]]:
    values: dict[str, dict[str, object]] = {
        "tooth": {
            "files": 0,
            "lines": 0,
            "empty_files": 0,
            "original_classes": Counter(),
            "nonzero_output_class_lines": 0,
        },
        "collision": {
            "files": 0,
            "lines": 0,
            "empty_files": 0,
            "original_classes": Counter(),
            "nonzero_output_class_lines": 0,
        },
    }
    for result in results:
        stats = values[result.category]
        stats["files"] = int(stats["files"]) + 1
        stats["lines"] = int(stats["lines"]) + result.line_count
        stats["empty_files"] = int(stats["empty_files"]) + int(result.empty)
        class_counter = stats["original_classes"]
        assert isinstance(class_counter, Counter)
        class_counter.update(result.original_classes)
    for stats in values.values():
        class_counter = stats["original_classes"]
        assert isinstance(class_counter, Counter)
        stats["original_classes"] = {
            str(key): class_counter[key] for key in sorted(class_counter)
        }
    return values


def _materialize_all(
    *,
    operations: Iterable[MaterializeOperation],
    config: RunConfig,
) -> tuple[Mapping[str, int], Mapping[str, int], Mapping[str, int]]:
    mode_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    image_mode_counts: Counter[str] = Counter()

    def run(operation: MaterializeOperation) -> MaterializeResult:
        return materialize_file(operation, config.output.unchanged_file_mode)

    results = bounded_parallel_map(
        run,
        operations,
        workers=config.performance.workers,
        max_in_flight=config.performance.max_in_flight,
        thread_name_prefix="formatter-materialize",
    )
    for result in results:
        mode_counts[result.mode] += 1
        category_counts[result.category] += 1
        if result.category == "image":
            image_mode_counts[result.mode] += 1
    return dict(mode_counts), dict(category_counts), dict(image_mode_counts)


def _transform_all_labels(
    *,
    plans: Sequence[FramePlan],
    staging_root: Path,
    config: RunConfig,
) -> Mapping[str, Mapping[str, object]]:
    def run(operation: tuple[str, Path, Path]) -> LabelTransformResult:
        category, source, destination = operation
        return transform_label_file(
            category=category,
            source=source,
            destination=destination,
        )

    results = bounded_parallel_map(
        run,
        _label_operations(plans, staging_root),
        workers=config.performance.workers,
        max_in_flight=config.performance.max_in_flight,
        thread_name_prefix="formatter-label",
    )
    return _aggregate_label_results(results)


def run_formatter(config: RunConfig) -> Mapping[str, object]:
    started = time.perf_counter()
    contract = discover_dataset(config.input_root)
    plans = build_frame_plans(contract, config.filename_prefix)
    staging = create_staging_directory(config.output_root)
    try:
        dataset = staging / "dataset"
        (dataset / "rgb").mkdir(parents=True, exist_ok=False)
        (dataset / "tooth_boxes").mkdir(parents=True, exist_ok=False)
        (dataset / "tooth_collision_model").mkdir(parents=True, exist_ok=False)

        preserved_operations = _collect_preserved_operations(config, staging)
        materialize_operations = itertools.chain(
            _image_operations(plans, staging), preserved_operations
        )
        mode_counts, materialize_category_counts, image_mode_counts = _materialize_all(
            operations=materialize_operations,
            config=config,
        )

        label_statistics = _transform_all_labels(
            plans=plans,
            staging_root=staging,
            config=config,
        )
        _write_class_file(
            dataset / "tooth_boxes" / "classes.txt",
            config.classes.tooth_class_name,
        )
        _write_class_file(
            dataset / "tooth_collision_model" / "classes.txt",
            config.classes.collision_class_name,
        )
        write_rename_manifest(staging / "rename_manifest.csv", plans)

        validate_staging_dataset(
            staging_root=staging,
            plans=plans,
            filename_prefix=config.filename_prefix,
            padding_width=contract.padding_width,
            tooth_class_name=config.classes.tooth_class_name,
            collision_class_name=config.classes.collision_class_name,
            label_statistics=label_statistics,
        )

        elapsed = time.perf_counter() - started
        total_materialized = sum(mode_counts.values())
        total_label_files = sum(
            int(stats["files"]) for stats in label_statistics.values()
        )
        total_files_processed = total_materialized + total_label_files
        manifest = {
            "schema_version": 1,
            "status": "completed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "config": config_snapshot(config),
            "naming": {
                "rule": "<filename_prefix>_<zero_padded_frame_id>.<extension>",
                "max_frame_id": contract.max_frame_id,
                "padding_width": contract.padding_width,
            },
            "frames": len(plans),
            "materialization": {
                "modes": mode_counts,
                "categories": materialize_category_counts,
                "image_modes": image_mode_counts,
            },
            "labels": label_statistics,
            "elapsed_seconds": round(elapsed, 6),
            "files_per_second": round(total_files_processed / elapsed, 3)
            if elapsed > 0
            else None,
            "rename_manifest": "rename_manifest.csv",
            "source_manifest": "source_manifest.json",
        }
        write_formatter_manifest(staging / "formatter_manifest.json", manifest)
        commit_staging(staging, config.output_root)
    except BaseException:
        discard_staging(staging)
        raise

    return {
        "status": "completed",
        "frames": len(plans),
        "max_frame_id": contract.max_frame_id,
        "padding_width": contract.padding_width,
        "images_linked": image_mode_counts.get("hardlink", 0),
        "images_copied": image_mode_counts.get("copy", 0),
        "tooth_label_files": label_statistics["tooth"]["files"],
        "collision_label_files": label_statistics["collision"]["files"],
        "label_lines_rewritten": int(label_statistics["tooth"]["lines"])
        + int(label_statistics["collision"]["lines"]),
        "empty_tooth_labels": label_statistics["tooth"]["empty_files"],
        "empty_collision_labels": label_statistics["collision"]["empty_files"],
        "elapsed_seconds": round(elapsed, 6),
        "files_per_second": round(total_files_processed / elapsed, 3)
        if elapsed > 0
        else None,
        "output_root": str(config.output_root),
    }
