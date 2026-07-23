"""Strict, versioned business configuration for one semantic-capture run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from render_profile import SUPPORTED_RENDERERS


CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSION = 1

_CONFIG_FIELDS = {
    "schema_version",
    "usd",
    "mapping",
    "camera_prim_path",
    "renderer",
    "render_profile",
    "warmup_render_frames",
    "rt_subframes",
    "output",
    "overwrite",
    "frames",
    "width",
    "height",
    "physics_hz",
    "capture_fps",
    "capture_mode",
    "capture_initial_frame",
    "pre_roll_steps",
    "enable_motion",
    "trajectory",
    "trajectory_mode",
    "interpolation",
    "joint_profile",
    "articulation_ready_timeout_steps",
    "headless",
    "save_runtime_ids",
    "strict_mapping",
    "strict_stage",
}

_PATH_FIELDS = (
    "usd",
    "mapping",
    "render_profile",
    "output",
    "trajectory",
    "joint_profile",
)


def _field_error(name: str, expected: str) -> ValueError:
    return ValueError(f"Configuration field {name!r} must be {expected}")


def _require_string(raw: dict[str, Any], name: str) -> str:
    value = raw[name]
    if not isinstance(value, str) or not value.strip():
        raise _field_error(name, "a non-empty string")
    return value.strip()


def _require_bool(raw: dict[str, Any], name: str) -> bool:
    value = raw[name]
    if type(value) is not bool:
        raise _field_error(name, "a JSON boolean")
    return value


def _require_integer(
    raw: dict[str, Any],
    name: str,
    *,
    minimum: int,
    nullable: bool = False,
) -> int | None:
    value = raw[name]
    if nullable and value is None:
        return None
    if type(value) is not int or value < minimum:
        qualifier = f"an integer greater than or equal to {minimum}"
        if nullable:
            qualifier += ", or null"
        raise _field_error(name, qualifier)
    return value


def _require_choice(
    raw: dict[str, Any],
    name: str,
    choices: tuple[str, ...],
) -> str:
    value = _require_string(raw, name)
    if value not in choices:
        raise ValueError(
            f"Configuration field {name!r} must be one of {choices}, got {value!r}"
        )
    return value


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


@dataclass(frozen=True)
class CaptureLaunchConfig:
    """Validated effective business inputs loaded before Isaac Sim starts."""

    source_path: Path
    schema_version: int
    usd: str
    mapping: str
    camera_prim_path: str
    renderer: str
    render_profile: str
    warmup_render_frames: int | None
    rt_subframes: int | None
    output: str
    overwrite: bool
    frames: int
    width: int
    height: int
    physics_hz: int
    capture_fps: int
    capture_mode: str
    capture_initial_frame: bool
    pre_roll_steps: int
    enable_motion: bool
    trajectory: str
    trajectory_mode: str
    interpolation: str
    joint_profile: str
    articulation_ready_timeout_steps: int
    headless: bool
    save_runtime_ids: bool
    strict_mapping: bool
    strict_stage: bool

    @classmethod
    def load(cls, path: str | Path) -> "CaptureLaunchConfig":
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Capture configuration file not found: {source_path}")
        try:
            with source_path.open("r", encoding="utf-8") as stream:
                raw = json.load(stream)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid capture configuration JSON at "
                f"{source_path}:{exc.lineno}:{exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(raw, dict):
            raise ValueError("Capture configuration root must be a JSON object")

        actual_fields = set(raw)
        unknown_fields = sorted(actual_fields - _CONFIG_FIELDS)
        if unknown_fields:
            details: list[str] = []
            for field_name in unknown_fields:
                suggestion = get_close_matches(field_name, _CONFIG_FIELDS, n=1)
                if suggestion:
                    details.append(f"{field_name!r} (did you mean {suggestion[0]!r}?)")
                else:
                    details.append(repr(field_name))
            raise ValueError(f"Unknown capture configuration field(s): {', '.join(details)}")
        missing_fields = sorted(_CONFIG_FIELDS - actual_fields)
        if missing_fields:
            raise ValueError(
                f"Missing capture configuration field(s): {', '.join(missing_fields)}"
            )

        schema_version = _require_integer(raw, "schema_version", minimum=1)
        if schema_version != CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported capture configuration schema version: {schema_version}; "
                f"expected {CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSION}"
            )

        string_values = {
            name: _require_string(raw, name)
            for name in (*_PATH_FIELDS, "camera_prim_path")
        }
        camera_prim_path = string_values["camera_prim_path"]
        if not camera_prim_path.startswith("/"):
            raise ValueError(
                "Configuration field 'camera_prim_path' must be an absolute USD Prim path"
            )

        base_dir = source_path.parent
        resolved_paths = {
            name: _resolve_path(string_values[name], base_dir) for name in _PATH_FIELDS
        }

        return cls(
            source_path=source_path,
            schema_version=schema_version,
            usd=resolved_paths["usd"],
            mapping=resolved_paths["mapping"],
            camera_prim_path=camera_prim_path,
            renderer=_require_choice(raw, "renderer", SUPPORTED_RENDERERS),
            render_profile=resolved_paths["render_profile"],
            warmup_render_frames=_require_integer(
                raw, "warmup_render_frames", minimum=0, nullable=True
            ),
            rt_subframes=_require_integer(raw, "rt_subframes", minimum=1, nullable=True),
            output=resolved_paths["output"],
            overwrite=_require_bool(raw, "overwrite"),
            frames=_require_integer(raw, "frames", minimum=1),
            width=_require_integer(raw, "width", minimum=1),
            height=_require_integer(raw, "height", minimum=1),
            physics_hz=_require_integer(raw, "physics_hz", minimum=1),
            capture_fps=_require_integer(raw, "capture_fps", minimum=1),
            capture_mode=_require_choice(raw, "capture_mode", ("static", "motion")),
            capture_initial_frame=_require_bool(raw, "capture_initial_frame"),
            pre_roll_steps=_require_integer(raw, "pre_roll_steps", minimum=0),
            enable_motion=_require_bool(raw, "enable_motion"),
            trajectory=resolved_paths["trajectory"],
            trajectory_mode=_require_choice(raw, "trajectory_mode", ("loop", "hold")),
            interpolation=_require_choice(raw, "interpolation", ("linear",)),
            joint_profile=resolved_paths["joint_profile"],
            articulation_ready_timeout_steps=_require_integer(
                raw, "articulation_ready_timeout_steps", minimum=1
            ),
            headless=_require_bool(raw, "headless"),
            save_runtime_ids=_require_bool(raw, "save_runtime_ids"),
            strict_mapping=_require_bool(raw, "strict_mapping"),
            strict_stage=_require_bool(raw, "strict_stage"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("source_path")
        return payload
