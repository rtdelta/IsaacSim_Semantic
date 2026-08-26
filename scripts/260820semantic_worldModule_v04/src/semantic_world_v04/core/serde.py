"""Strict serialization helpers with deterministic JSON output."""

import dataclasses
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Set

from .errors import SchemaError


def expect_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError("expected an object", path)
    return value


def expect_list(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SchemaError("expected an array", path)
    return value


def expect_string(value: Any, path: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SchemaError("expected a string", path)
    if not allow_empty and not value.strip():
        raise SchemaError("must not be empty", path)
    return value


def expect_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaError("expected a boolean", path)
    return value


def expect_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("expected an integer", path)
    return value


def expect_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError("expected a number", path)
    return float(value)


def strict_keys(
    data: Mapping[str, Any],
    *,
    allowed: Iterable[str],
    required: Iterable[str] = (),
    path: str,
) -> None:
    allowed_set: Set[str] = set(allowed)
    required_set: Set[str] = set(required)
    unknown = sorted(set(data) - allowed_set)
    missing = sorted(required_set - set(data))
    if unknown:
        raise SchemaError(f"unknown field(s): {', '.join(unknown)}", path)
    if missing:
        raise SchemaError(f"missing field(s): {', '.join(missing)}", path)


def string_list(value: Any, path: str) -> list:
    return [
        expect_string(item, f"{path}[{index}]")
        for index, item in enumerate(expect_list(value, path))
    ]


def string_dict(value: Any, path: str) -> Dict[str, str]:
    mapping = expect_mapping(value, path)
    result: Dict[str, str] = {}
    for key, item in mapping.items():
        parsed_key = expect_string(key, f"{path}.<key>")
        result[parsed_key] = expect_string(item, f"{path}.{parsed_key}", allow_empty=True)
    return result


def json_object(value: Any, path: str) -> Dict[str, Any]:
    mapping = expect_mapping(value, path)
    result = dict(mapping)
    try:
        canonical_json(result)
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"must contain JSON-compatible values: {exc}", path) from exc
    return result


def to_data(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: to_data(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [to_data(item) for item in value]
    if isinstance(value, list):
        return [to_data(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): to_data(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_data(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def pretty_json(value: Any) -> str:
    return json.dumps(
        to_data(value),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

