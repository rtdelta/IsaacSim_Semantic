from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Mapping, Sequence

from .config import RunConfig
from .models import InputContract


def _load_json_object(path: Path, description: str) -> Dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"cannot read {description}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} must contain a JSON object")
    return value


def _manifest_string(
    manifest: Mapping[str, object],
    section: str,
    key: str,
    description: str,
) -> str:
    container = manifest.get(section)
    if not isinstance(container, dict):
        raise ValueError(f"{description}.{section} must be an object")
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description}.{section}.{key} must be a string")
    return value.strip()


def _normalized_path_text(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def _sha256_files(paths: Sequence[Path], extra: str) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    digest.update(extra.encode("ascii"))
    return digest.hexdigest()


def _manifest_targets(manifest: Mapping[str, object]) -> Sequence[str]:
    raw = manifest.get("targets")
    if not isinstance(raw, list):
        raise ValueError("ratio manifest.targets must be an array")
    labels = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"ratio manifest.targets[{index}] must be an object")
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(
                f"ratio manifest.targets[{index}].label must be a string"
            )
        labels.append(label.strip())
    return labels


def run_preflight(config: RunConfig) -> InputContract:
    post = config.inputs.postprocess
    ratio = config.inputs.pixel_ratio

    required_files = [
        (post.manifest, "PostProcess manifest"),
        (ratio.manifest, "PixelRatio manifest"),
        (post.tooth_module_dir / "classes.txt", "tooth classes"),
        (post.group_module_dir / "classes.txt", "group classes"),
    ]
    ratio_data_path = (
        ratio.counts_cache
        if ratio.input_format == "counts_cache_npz"
        else ratio.per_frame_csv
    )
    required_files.append((ratio_data_path, "ratio input"))
    for path, description in required_files:
        if not path.is_file():
            raise FileNotFoundError(f"{description} does not exist: {path}")
    for directory, description in (
        (post.tooth_module_dir, "tooth module directory"),
        (post.group_module_dir, "group module directory"),
    ):
        if not directory.is_dir():
            raise FileNotFoundError(f"{description} does not exist: {directory}")
    for path, description in (
        (post.tooth_module_dir / "classes.txt", "tooth classes"),
        (post.group_module_dir / "classes.txt", "group classes"),
    ):
        class_names = [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if not class_names:
            raise ValueError(f"{description} file must not be empty: {path}")

    post_manifest = _load_json_object(post.manifest, "PostProcess manifest")
    ratio_manifest = _load_json_object(ratio.manifest, "PixelRatio manifest")
    if post_manifest.get("status") != "completed":
        raise ValueError("PostProcess manifest status must be completed")
    if ratio_manifest.get("status") != "completed":
        raise ValueError("PixelRatio manifest status must be completed")

    post_semantic = _manifest_string(
        post_manifest, "inputs", "semantic_dir", "PostProcess manifest"
    )
    ratio_semantic = _manifest_string(
        ratio_manifest,
        "inputs",
        "whole_scene_semantic_dir",
        "PixelRatio manifest",
    )
    if _normalized_path_text(post_semantic) != _normalized_path_text(
        ratio_semantic
    ):
        raise ValueError(
            "PostProcess semantic_dir does not match PixelRatio "
            "whole_scene_semantic_dir"
        )

    post_mapping = _manifest_string(
        post_manifest, "inputs", "semantic_mapping", "PostProcess manifest"
    )
    ratio_mapping = _manifest_string(
        ratio_manifest, "inputs", "semantic_mapping", "PixelRatio manifest"
    )
    if _normalized_path_text(post_mapping) != _normalized_path_text(
        ratio_mapping
    ):
        raise ValueError(
            "PostProcess and PixelRatio semantic mapping paths do not match"
        )

    manifest_labels = tuple(_manifest_targets(ratio_manifest))
    if manifest_labels != config.targets.labels_in_physical_order:
        raise ValueError(
            "PixelRatio target label order does not match configured physical order; "
            f"manifest={manifest_labels}, "
            f"config={config.targets.labels_in_physical_order}"
        )
    group_name = ratio_manifest.get("group_name")
    if group_name != config.targets.group_name:
        raise ValueError(
            "PixelRatio group_name does not match configured group_name"
        )

    if config.output.root.exists():
        if not config.output.root.is_dir():
            raise ValueError(
                f"output root exists but is not a directory: {config.output.root}"
            )
        if not config.output.overwrite:
            raise FileExistsError(
                f"output root already exists: {config.output.root}"
            )

    config_fingerprint = config.fingerprint()
    input_fingerprint = _sha256_files(
        (
            post.manifest,
            ratio.manifest,
            ratio_data_path,
            post.tooth_module_dir / "classes.txt",
            post.group_module_dir / "classes.txt",
        ),
        config_fingerprint,
    )
    return InputContract(
        postprocess_manifest=post_manifest,
        ratio_manifest=ratio_manifest,
        postprocess_manifest_path=post.manifest,
        ratio_manifest_path=ratio.manifest,
        tooth_module_dir=post.tooth_module_dir,
        group_module_dir=post.group_module_dir,
        ratio_data_path=ratio_data_path,
        input_fingerprint=input_fingerprint,
        config_fingerprint=config_fingerprint,
    )
