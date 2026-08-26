from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .models import ClassesConfig, OutputConfig, PerformanceConfig, RunConfig


SUPPORTED_SCHEMA_VERSION = 1
UNCHANGED_FILE_MODES = {"hardlink_or_copy", "hardlink_required", "copy"}


def _object(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return value


def _reject_unknown(
    value: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} has unknown fields: {', '.join(unknown)}")


def _string(value: Mapping[str, Any], key: str, context: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return result


def _integer(value: Mapping[str, Any], key: str, context: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return result


def _boolean(value: Mapping[str, Any], key: str, context: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return result


def _resolve(base: Path, raw: str) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_prefix(prefix: str) -> None:
    if prefix != prefix.strip():
        raise ValueError("filename_prefix must not have leading or trailing whitespace")
    if prefix in {".", ".."}:
        raise ValueError("filename_prefix cannot be '.' or '..'")
    if prefix.endswith("_"):
        raise ValueError("filename_prefix must not end with '_'")
    if any(character in "/\\" for character in prefix):
        raise ValueError("filename_prefix must not contain path separators")
    if any(ord(character) < 32 or ord(character) == 127 for character in prefix):
        raise ValueError("filename_prefix must not contain control characters")


def _validate_class_name(value: str, context: str) -> None:
    if value != value.strip():
        raise ValueError(f"{context} must not have leading or trailing whitespace")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{context} must be a single line")


def load_config(path: Path) -> RunConfig:
    config_path = path.expanduser().resolve(strict=True)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {config_path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    root = _object(raw, "config")
    _reject_unknown(
        root,
        {
            "schema_version",
            "input_root",
            "output_root",
            "filename_prefix",
            "classes",
            "output",
            "performance",
        },
        "config",
    )

    schema_version = _integer(root, "schema_version", "config")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {schema_version}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}"
        )

    base = config_path.parent
    input_root = _resolve(base, _string(root, "input_root", "config"))
    output_root = _resolve(base, _string(root, "output_root", "config"))
    if not input_root.is_dir():
        raise ValueError(f"input_root is not a directory: {input_root}")
    if output_root.exists():
        raise FileExistsError(f"output_root already exists: {output_root}")
    if (
        input_root == output_root
        or _is_relative_to(output_root, input_root)
        or _is_relative_to(input_root, output_root)
    ):
        raise ValueError(
            "input_root and output_root must be separate, non-nested directories"
        )

    filename_prefix = _string(root, "filename_prefix", "config")
    _validate_prefix(filename_prefix)

    classes_raw = _object(root.get("classes"), "config.classes")
    _reject_unknown(
        classes_raw,
        {"tooth_class_name", "collision_class_name"},
        "config.classes",
    )
    tooth_class_name = _string(
        classes_raw, "tooth_class_name", "config.classes"
    )
    collision_class_name = _string(
        classes_raw, "collision_class_name", "config.classes"
    )
    _validate_class_name(tooth_class_name, "config.classes.tooth_class_name")
    _validate_class_name(
        collision_class_name, "config.classes.collision_class_name"
    )

    output_raw = _object(root.get("output"), "config.output")
    _reject_unknown(
        output_raw,
        {"preserve_reports", "unchanged_file_mode"},
        "config.output",
    )
    preserve_reports = _boolean(
        output_raw, "preserve_reports", "config.output"
    )
    unchanged_file_mode = _string(
        output_raw, "unchanged_file_mode", "config.output"
    )
    if unchanged_file_mode not in UNCHANGED_FILE_MODES:
        raise ValueError(
            "config.output.unchanged_file_mode must be one of: "
            + ", ".join(sorted(UNCHANGED_FILE_MODES))
        )

    performance_raw = _object(root.get("performance"), "config.performance")
    _reject_unknown(
        performance_raw, {"workers", "max_in_flight"}, "config.performance"
    )
    workers = _integer(performance_raw, "workers", "config.performance")
    max_in_flight = _integer(
        performance_raw, "max_in_flight", "config.performance"
    )
    if workers <= 0:
        raise ValueError("config.performance.workers must be positive")
    if max_in_flight <= 0:
        raise ValueError("config.performance.max_in_flight must be positive")

    return RunConfig(
        schema_version=schema_version,
        config_path=config_path,
        input_root=input_root,
        output_root=output_root,
        filename_prefix=filename_prefix,
        classes=ClassesConfig(
            tooth_class_name=tooth_class_name,
            collision_class_name=collision_class_name,
        ),
        output=OutputConfig(
            preserve_reports=preserve_reports,
            unchanged_file_mode=unchanged_file_mode,
        ),
        performance=PerformanceConfig(
            workers=workers,
            max_in_flight=max_in_flight,
        ),
    )
