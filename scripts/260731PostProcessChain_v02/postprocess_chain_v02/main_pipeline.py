from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Mapping, Tuple

from .cache.feature_cache import load_feature_cache, write_feature_cache
from .cache.fingerprint import build_analysis_fingerprint, build_run_fingerprint
from .config import RunConfig, resolved_config_dict
from .executor import execute_analysis
from .models import CollisionBoxResult, FeatureMatrix
from .modules.collision_box.module import build_collision_box
from .modules.threshold_rules.module import build_rule_masks
from .output.atomic_io import write_json
from .output.dataset_writer import DatasetWriter
from .output.reporter import write_reports
from .output.staging import (
    commit_staging,
    create_staging_directory,
    discard_staging,
)
from .preflight import run_preflight


PIPELINE_VERSION = "3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_collisions(
    config: RunConfig,
    features: FeatureMatrix,
    collision_keep,
) -> Tuple[CollisionBoxResult, ...]:
    values = []
    for index, frame_id in enumerate(features.frame_ids):
        values.append(
            build_collision_box(
                frame_id=frame_id,
                full_boxes=features.full_axis_boxes[index],
                reference_boxes=features.reference_axis_boxes[index],
                full_valid=features.full_geometry_valid[index],
                reference_valid=features.reference_geometry_valid[index],
                collision_keep=bool(collision_keep[index]),
                image_width=int(features.image_widths[index]),
                image_height=int(features.image_heights[index]),
                config=config.modules.collision_box,
            )
        )
    return tuple(values)


def run_pipeline(config: RunConfig) -> Mapping[str, object]:
    started = time.perf_counter()
    contract = run_preflight(config)
    labels = tuple(item.semantic_label for item in config.targets.teeth)
    analysis_fingerprint = build_analysis_fingerprint(config, contract)
    run_fingerprint = build_run_fingerprint(config, analysis_fingerprint)

    features = None
    cache_used = False
    if config.cache.enabled and config.cache.reuse:
        features = load_feature_cache(
            config.cache.directory,
            analysis_fingerprint,
            labels,
        )
        cache_used = features is not None
    if config.pipeline.mode == "filter_only" and features is None:
        raise ValueError(
            "filter_only requires a complete feature cache with a matching "
            "Analysis fingerprint"
        )
    if features is None:
        frame_features = execute_analysis(contract, config)
        features = FeatureMatrix.from_frames(frame_features)
        if config.cache.enabled:
            write_feature_cache(
                config.cache.directory,
                features,
                analysis_fingerprint,
                labels,
            )
    expected_ids = tuple(task.frame_id for task in contract.tasks)
    if features.frame_ids != expected_ids:
        raise ValueError(
            "feature cache frame IDs do not match the current input contract"
        )

    masks = build_rule_masks(features, config.modules.threshold_rules)
    collisions = _build_collisions(config, features, masks.collision_keep)
    staging = create_staging_directory(config.output.root)
    try:
        write_json(staging / "resolved_config.json", resolved_config_dict(config))
        if config.pipeline.mode != "analyze_only":
            writer = DatasetWriter(staging, config)
            writer.write_all(contract.tasks, features, masks, collisions)
            verified_frames = writer.verify(contract.tasks)
        else:
            verified_frames = 0
        summary = write_reports(staging, config, features, masks, collisions)
        elapsed = time.perf_counter() - started
        manifest = {
            "schema_version": 2,
            "pipeline_version": PIPELINE_VERSION,
            "status": "completed",
            "finished_at": _utc_now(),
            "mode": config.pipeline.mode,
            "config_path": str(config.config_path),
            "analysis_fingerprint": analysis_fingerprint,
            "run_fingerprint": run_fingerprint,
            "cache": {
                "enabled": config.cache.enabled,
                "used": cache_used,
                "directory": str(config.cache.directory),
            },
            "inputs": {
                "full_scene_rgb_dir": str(config.inputs.full_scene.rgb_dir),
                "full_scene_semantic_dir": str(config.inputs.full_scene.semantic_dir),
                "reference_capture_variant": config.inputs.reference.capture_variant,
                "reference_semantic_dir": str(config.inputs.reference.semantic_dir),
                "semantic_mapping": str(config.inputs.semantic_mapping),
            },
            "frames": len(features.frame_ids),
            "verified_frames": verified_frames,
            "elapsed_seconds": round(elapsed, 6),
            "summary": dict(summary),
        }
        write_json(staging / "manifest.json", manifest)
        commit_staging(staging, config.output.root, config.output.overwrite)
        return manifest
    except BaseException:
        discard_staging(staging)
        raise
