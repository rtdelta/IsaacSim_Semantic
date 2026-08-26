"""Strict configuration for the optional Prim-whitelist render pass."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


ISOLATED_RENDER_CONFIG_SCHEMA_VERSION = 1
_CONFIG_FIELDS = {"schema_version", "render_prim_paths"}


def _is_descendant(path: PurePosixPath, root: PurePosixPath) -> bool:
    return len(root.parts) < len(path.parts) and path.parts[: len(root.parts)] == root.parts


def _validate_prim_path(value: Any, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"render_prim_paths[{index}] must be a non-empty string")
    normalized = str(PurePosixPath(value.strip()))
    if not normalized.startswith("/") or normalized == "/":
        raise ValueError(
            f"render_prim_paths[{index}] must be an absolute USD Prim path below '/': "
            f"{value!r}"
        )
    if "//" in value or any(part in {".", ".."} for part in PurePosixPath(value).parts):
        raise ValueError(f"render_prim_paths[{index}] is not normalized: {value!r}")
    return normalized


@dataclass(frozen=True)
class IsolatedRenderConfig:
    """Validated root Prim paths retained during the isolated render."""

    source_path: Path
    schema_version: int
    render_prim_paths: tuple[str, ...]

    @classmethod
    def load(cls, path: str | Path) -> "IsolatedRenderConfig":
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Isolated-render Prim configuration file not found: {source_path}"
            )
        try:
            with source_path.open("r", encoding="utf-8") as stream:
                raw = json.load(stream)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid isolated-render configuration JSON at "
                f"{source_path}:{exc.lineno}:{exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(raw, dict):
            raise ValueError("Isolated-render configuration root must be a JSON object")

        actual_fields = set(raw)
        unknown_fields = sorted(actual_fields - _CONFIG_FIELDS)
        missing_fields = sorted(_CONFIG_FIELDS - actual_fields)
        if unknown_fields:
            raise ValueError(
                "Unknown isolated-render configuration field(s): "
                + ", ".join(unknown_fields)
            )
        if missing_fields:
            raise ValueError(
                "Missing isolated-render configuration field(s): "
                + ", ".join(missing_fields)
            )

        schema_version = raw["schema_version"]
        if type(schema_version) is not int:
            raise ValueError("schema_version must be a JSON integer")
        if schema_version != ISOLATED_RENDER_CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported isolated-render schema version: {schema_version}; "
                f"expected {ISOLATED_RENDER_CONFIG_SCHEMA_VERSION}"
            )

        raw_paths = raw["render_prim_paths"]
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError("render_prim_paths must be a non-empty JSON array")
        paths = tuple(_validate_prim_path(value, index) for index, value in enumerate(raw_paths))
        if len(set(paths)) != len(paths):
            raise ValueError("render_prim_paths must not contain duplicate paths")

        pure_paths = tuple(PurePosixPath(value) for value in paths)
        for index, path_value in enumerate(pure_paths):
            for other_index, other_value in enumerate(pure_paths):
                if index == other_index:
                    continue
                if _is_descendant(path_value, other_value):
                    raise ValueError(
                        "render_prim_paths contains a redundant descendant path: "
                        f"{path_value} is already included by {other_value}"
                    )

        return cls(
            source_path=source_path,
            schema_version=schema_version,
            render_prim_paths=paths,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_path": str(self.source_path),
            "render_prim_paths": list(self.render_prim_paths),
        }
