from __future__ import annotations

import hashlib
import json
from pathlib import Path
from ..config import RunConfig
from ..models import InputContract


def _update_file_metadata(digest, path: Path, content: bool) -> None:
    stat = path.stat()
    digest.update(str(path).encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(stat.st_size).encode("ascii"))
    digest.update(b"\0")
    digest.update(str(stat.st_mtime_ns).encode("ascii"))
    digest.update(b"\0")
    if content:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)


def build_analysis_fingerprint(
    config: RunConfig,
    contract: InputContract,
) -> str:
    digest = hashlib.sha256()
    content = config.cache.fingerprint_mode == "content"
    _update_file_metadata(digest, config.inputs.semantic_mapping, content)
    for task in contract.tasks:
        for path in (
            task.full_rgb_path,
            task.full_semantic_path,
            task.reference_semantic_path,
        ):
            _update_file_metadata(digest, path, content)
    structure = {
        "schema_version": 2,
        "target_ids": list(contract.target_ids),
        "targets": [
            {
                "class_id": item.class_id,
                "class_name": item.class_name,
                "semantic_label": item.semantic_label,
            }
            for item in config.targets.teeth
        ],
        "shape": list(contract.shape),
        "dtype": contract.expected_dtype,
        "mapping_sha256": contract.mapping_sha256,
        "semantic_features": {
            "target_extraction": config.modules.semantic_features.target_extraction
        },
        "reference": {
            "capture_variant": config.inputs.reference.capture_variant,
        },
        "component_filter": {
            "enabled": config.modules.component_filter.enabled,
            "connectivity": config.modules.component_filter.connectivity,
            "minimum_connected_component_pixels": (
                config.modules.component_filter.minimum_connected_component_pixels
            ),
        },
        "pose_metrics": {
            "algorithm": config.modules.pose_metrics.algorithm,
            "invalid_value": config.modules.pose_metrics.invalid_value,
        },
        "single_tooth_boxes": {
            "minimum_pixels": config.modules.single_tooth_boxes.minimum_pixels
        },
        "visibility_ratio": {
            "zero_reference_value": config.modules.visibility_ratio.zero_reference_value,
            "ratio_over_one": config.modules.visibility_ratio.ratio_over_one,
        },
    }
    digest.update(
        json.dumps(structure, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return digest.hexdigest()


def build_run_fingerprint(config: RunConfig, analysis_fingerprint: str) -> str:
    structure = {
        "analysis_fingerprint": analysis_fingerprint,
        "threshold_rules": {
            "single": {
                "a": config.modules.threshold_rules.single_tooth.minimum_visible_ratio_a,
                "c": config.modules.threshold_rules.single_tooth.minimum_fill_ratio_c,
                "height_width_axis_mode": config.modules.threshold_rules.single_tooth.height_width_axis_mode,
                "d": config.modules.threshold_rules.single_tooth.minimum_height_width_ratio_d,
                "bad_count": config.modules.threshold_rules.single_tooth.drop_all_single_boxes_if_bad_teeth_at_least,
            },
            "collision": {
                "b": config.modules.threshold_rules.collision_model.minimum_visible_ratio_b,
                "bad_count": config.modules.threshold_rules.collision_model.drop_collision_box_if_bad_teeth_at_least,
            },
        },
        "collision_box": {
            "length_axis": config.modules.collision_box.length_axis,
            "length_source": config.modules.collision_box.length_source,
            "width_source": config.modules.collision_box.width_source,
            "union_scope": config.modules.collision_box.union_scope,
        },
        "reporting": {
            "level": config.reporting.level,
            "write_angle": config.modules.pose_metrics.write_angle,
        },
        "targets": {
            "teeth": [item.class_name for item in config.targets.teeth],
            "collision": config.targets.collision_model.class_name,
        },
        "output": {
            "keep_empty_label_files": config.output.keep_empty_label_files,
        },
    }
    return hashlib.sha256(
        json.dumps(structure, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
