from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import numpy as np

from ..models import FeatureMatrix


CACHE_SCHEMA_VERSION = 2


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_paths(directory: Path) -> tuple[Path, Path]:
    return directory / "features_cache.npz", directory / "cache_manifest.json"


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_feature_cache(
    directory: Path,
    features: FeatureMatrix,
    analysis_fingerprint: str,
    labels: tuple[str, ...],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data_path, manifest_path = cache_paths(directory)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{data_path.name}.", suffix=".tmp", dir=directory
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(
                handle,
                frame_ids=np.asarray(features.frame_ids, dtype=np.str_),
                image_widths=features.image_widths,
                image_heights=features.image_heights,
                whole_raw_counts=features.whole_raw_counts,
                whole_counts=features.whole_counts,
                reference_raw_counts=features.reference_raw_counts,
                reference_counts=features.reference_counts,
                full_kept_component_counts=features.full_kept_component_counts,
                full_removed_component_counts=features.full_removed_component_counts,
                full_removed_pixel_counts=features.full_removed_pixel_counts,
                reference_kept_component_counts=features.reference_kept_component_counts,
                reference_removed_component_counts=features.reference_removed_component_counts,
                reference_removed_pixel_counts=features.reference_removed_pixel_counts,
                visibility_ratios=features.visibility_ratios,
                ratio_statuses=features.ratio_statuses,
                full_axis_boxes=features.full_axis_boxes,
                reference_axis_boxes=features.reference_axis_boxes,
                full_geometry_valid=features.full_geometry_valid,
                reference_geometry_valid=features.reference_geometry_valid,
                reference_fill_ratios=features.reference_fill_ratios,
                reference_aspect_ratios=features.reference_aspect_ratios,
                reference_angles=features.reference_angles,
                reference_pose_statuses=features.reference_pose_statuses,
                source_box_exists=features.source_box_exists,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, data_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    _atomic_json(
        manifest_path,
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "status": "completed",
            "created_at": _utc_now(),
            "analysis_fingerprint": analysis_fingerprint,
            "frames": len(features.frame_ids),
            "labels": list(labels),
            "cache_file": data_path.name,
        },
    )


def load_feature_cache(
    directory: Path,
    expected_fingerprint: str,
    expected_labels: tuple[str, ...],
) -> FeatureMatrix | None:
    data_path, manifest_path = cache_paths(directory)
    if not data_path.is_file() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read cache manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != CACHE_SCHEMA_VERSION:
        raise ValueError("unsupported cache manifest schema")
    if manifest.get("status") != "completed":
        raise ValueError("cache manifest status must be completed")
    if manifest.get("analysis_fingerprint") != expected_fingerprint:
        return None
    if tuple(manifest.get("labels", ())) != expected_labels:
        return None

    with np.load(data_path, allow_pickle=False) as archive:
        required = {
            "frame_ids",
            "image_widths",
            "image_heights",
            "whole_raw_counts",
            "whole_counts",
            "reference_raw_counts",
            "reference_counts",
            "full_kept_component_counts",
            "full_removed_component_counts",
            "full_removed_pixel_counts",
            "reference_kept_component_counts",
            "reference_removed_component_counts",
            "reference_removed_pixel_counts",
            "visibility_ratios",
            "ratio_statuses",
            "full_axis_boxes",
            "reference_axis_boxes",
            "full_geometry_valid",
            "reference_geometry_valid",
            "reference_fill_ratios",
            "reference_aspect_ratios",
            "reference_angles",
            "reference_pose_statuses",
            "source_box_exists",
        }
        missing = sorted(required - set(archive.files))
        if missing:
            raise ValueError("feature cache is missing arrays: " + ", ".join(missing))
        return FeatureMatrix(
            frame_ids=tuple(str(value) for value in archive["frame_ids"].tolist()),
            image_widths=np.asarray(archive["image_widths"]),
            image_heights=np.asarray(archive["image_heights"]),
            whole_raw_counts=np.asarray(archive["whole_raw_counts"]),
            whole_counts=np.asarray(archive["whole_counts"]),
            reference_raw_counts=np.asarray(archive["reference_raw_counts"]),
            reference_counts=np.asarray(archive["reference_counts"]),
            full_kept_component_counts=np.asarray(
                archive["full_kept_component_counts"]
            ),
            full_removed_component_counts=np.asarray(
                archive["full_removed_component_counts"]
            ),
            full_removed_pixel_counts=np.asarray(
                archive["full_removed_pixel_counts"]
            ),
            reference_kept_component_counts=np.asarray(
                archive["reference_kept_component_counts"]
            ),
            reference_removed_component_counts=np.asarray(
                archive["reference_removed_component_counts"]
            ),
            reference_removed_pixel_counts=np.asarray(
                archive["reference_removed_pixel_counts"]
            ),
            visibility_ratios=np.asarray(archive["visibility_ratios"]),
            ratio_statuses=np.asarray(archive["ratio_statuses"]),
            full_axis_boxes=np.asarray(archive["full_axis_boxes"]),
            reference_axis_boxes=np.asarray(archive["reference_axis_boxes"]),
            full_geometry_valid=np.asarray(archive["full_geometry_valid"]),
            reference_geometry_valid=np.asarray(archive["reference_geometry_valid"]),
            reference_fill_ratios=np.asarray(archive["reference_fill_ratios"]),
            reference_aspect_ratios=np.asarray(archive["reference_aspect_ratios"]),
            reference_angles=np.asarray(archive["reference_angles"]),
            reference_pose_statuses=np.asarray(archive["reference_pose_statuses"]),
            source_box_exists=np.asarray(archive["source_box_exists"]),
        )
