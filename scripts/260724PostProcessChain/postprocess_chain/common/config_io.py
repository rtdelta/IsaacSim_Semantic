from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .models import ModuleOutputConfig


def load_json_object(path: Path, description: str) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{description} JSON is invalid at line {exc.lineno}, column {exc.colno}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return value


def reject_unknown_fields(
    raw: Mapping[str, Any],
    allowed: Iterable[str],
    context: str,
) -> None:
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def require_object(raw: Mapping[str, Any], key: str, context: str) -> Dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{context}.{key} must be a JSON object")
    return value


def require_list(raw: Mapping[str, Any], key: str, context: str) -> List[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{context}.{key} must be a JSON array")
    return value


def require_string(raw: Mapping[str, Any], key: str, context: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def optional_string(
    raw: Mapping[str, Any],
    key: str,
    default: str,
    context: str,
) -> str:
    if key not in raw:
        return default
    return require_string(raw, key, context)


def require_integer(
    raw: Mapping[str, Any],
    key: str,
    context: str,
    minimum: int | None = None,
) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{context}.{key} must be >= {minimum}")
    return value


def optional_integer(
    raw: Mapping[str, Any],
    key: str,
    default: int,
    context: str,
    minimum: int | None = None,
) -> int:
    if key not in raw:
        return default
    return require_integer(raw, key, context, minimum)


def optional_boolean(
    raw: Mapping[str, Any],
    key: str,
    default: bool,
    context: str,
) -> bool:
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def resolve_path(value: str, base_directory: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_directory / path
    return path.resolve()


def parse_module_output(
    raw: Mapping[str, Any],
    context: str,
    output_root: Path,
) -> ModuleOutputConfig:
    reject_unknown_fields(raw, {"directory", "layout"}, context)
    directory_text = require_string(raw, "directory", context)
    directory_path = Path(directory_text)
    if directory_path.is_absolute():
        raise ValueError(f"{context}.directory must be relative to output_root")

    resolved = (output_root / directory_path).resolve()
    if output_root != resolved and output_root not in resolved.parents:
        raise ValueError(f"{context}.directory escapes output_root")

    layout = optional_string(raw, "layout", "flat_yolo", context)
    if layout != "flat_yolo":
        raise ValueError(f"{context}.layout currently supports only 'flat_yolo'")
    return ModuleOutputConfig(directory=resolved, layout=layout)
