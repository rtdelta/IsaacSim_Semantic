"""Strict, versioned business configuration for one semantic-capture run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from difflib import get_close_matches
from pathlib import Path, PurePosixPath
from typing import Any

from render_profile import SUPPORTED_RENDERERS


CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSION = 4
SUPPORTED_CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSIONS = (3, 4)

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
    "image_output_folders",
    "excavator_only_capture",
    "front_teeth_only_capture",
    "variant_transition",
    "variant_validation",
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

_VERSION_4_FIELDS = {
    "variant_transition",
    "variant_validation",
}

_VERSION_3_FIELDS = _CONFIG_FIELDS - _VERSION_4_FIELDS

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


def _require_object(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw[name]
    if not isinstance(value, dict):
        raise _field_error(name, "a JSON object")
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


def _require_string_tuple(
    raw: dict[str, Any],
    name: str,
    *,
    nullable: bool = False,
) -> tuple[str, ...] | None:
    value = raw[name]
    if nullable and value is None:
        return None
    if not isinstance(value, list):
        expected = "a JSON array of non-empty strings"
        if nullable:
            expected += ", or null"
        raise _field_error(name, expected)
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _field_error(f"{name}[{index}]", "a non-empty string")
        label = item.strip()
        key = label.casefold()
        if key in seen:
            raise ValueError(f"Configuration field {name!r} contains duplicate label {label!r}")
        seen.add(key)
        normalized.append(label)
    return tuple(normalized)


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def _normalize_output_folder(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _field_error(field_name, "a non-empty relative directory")
    normalized = PurePosixPath(value.strip().replace("\\", "/"))
    if normalized.is_absolute() or normalized == PurePosixPath(".") or ".." in normalized.parts:
        raise _field_error(
            field_name,
            "a relative directory below the configured output root without '..'",
        )
    if normalized.parts and normalized.parts[0] == ".frame_staging":
        raise _field_error(
            field_name,
            "a directory outside the reserved .frame_staging transaction root",
        )
    return str(normalized)


def _is_path_ancestor(parent: PurePosixPath, child: PurePosixPath) -> bool:
    return len(parent.parts) < len(child.parts) and child.parts[: len(parent.parts)] == parent.parts


@dataclass(frozen=True)
class ImageOutputFolders:
    """Relative business directories for all configured render variants."""

    full_scene_rgb: str
    full_scene_semantic: str
    excavator_only_rgb: str
    excavator_only_semantic: str
    front_teeth_only_rgb: str
    front_teeth_only_semantic: str

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "ImageOutputFolders":
        expected = {
            "full_scene_rgb",
            "full_scene_semantic",
            "excavator_only_rgb",
            "excavator_only_semantic",
            "front_teeth_only_rgb",
            "front_teeth_only_semantic",
        }
        actual = set(raw)
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        if unknown:
            raise ValueError(
                "Unknown image_output_folders field(s): " + ", ".join(unknown)
            )
        if missing:
            raise ValueError(
                "Missing image_output_folders field(s): " + ", ".join(missing)
            )
        values = {
            name: _normalize_output_folder(raw[name], f"image_output_folders.{name}")
            for name in expected
        }
        paths = {name: PurePosixPath(value) for name, value in values.items()}
        for left_name, left_path in paths.items():
            for right_name, right_path in paths.items():
                if left_name >= right_name:
                    continue
                if (
                    left_path == right_path
                    or _is_path_ancestor(left_path, right_path)
                    or _is_path_ancestor(right_path, left_path)
                ):
                    raise ValueError(
                        "Image output folders must be distinct and non-overlapping: "
                        f"{left_name}={left_path}, {right_name}={right_path}"
                    )
        return cls(**values)


@dataclass(frozen=True)
class ExcavatorOnlyCaptureConfig:
    """Optional second render pass and its external Prim whitelist."""

    enabled: bool
    render_prim_paths_config: str | None

    @classmethod
    def load(
        cls,
        raw: dict[str, Any],
        *,
        base_dir: Path,
    ) -> "ExcavatorOnlyCaptureConfig":
        expected = {"enabled", "render_prim_paths_config"}
        actual = set(raw)
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        if unknown:
            raise ValueError(
                "Unknown excavator_only_capture field(s): " + ", ".join(unknown)
            )
        if missing:
            raise ValueError(
                "Missing excavator_only_capture field(s): " + ", ".join(missing)
            )
        enabled = _require_bool(raw, "enabled")
        path_value = raw["render_prim_paths_config"]
        if path_value is None:
            resolved_path = None
        elif isinstance(path_value, str) and path_value.strip():
            resolved_path = _resolve_path(path_value.strip(), base_dir)
        else:
            raise _field_error(
                "excavator_only_capture.render_prim_paths_config",
                "a non-empty path string or null",
            )
        if enabled and resolved_path is None:
            raise ValueError(
                "excavator_only_capture.render_prim_paths_config is required when "
                "excavator_only_capture.enabled is true"
            )
        return cls(enabled=enabled, render_prim_paths_config=resolved_path)


@dataclass(frozen=True)
class FrontTeethOnlyCaptureConfig:
    """Optional third render pass retaining only the five front-tooth subtrees."""

    enabled: bool
    render_prim_paths_config: str | None
    save_rgb: bool

    @classmethod
    def load(
        cls,
        raw: dict[str, Any],
        *,
        base_dir: Path,
    ) -> "FrontTeethOnlyCaptureConfig":
        expected = {"enabled", "render_prim_paths_config", "save_rgb"}
        actual = set(raw)
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        if unknown:
            raise ValueError(
                "Unknown front_teeth_only_capture field(s): " + ", ".join(unknown)
            )
        if missing:
            raise ValueError(
                "Missing front_teeth_only_capture field(s): " + ", ".join(missing)
            )
        enabled = _require_bool(raw, "enabled")
        save_rgb = _require_bool(raw, "save_rgb")
        path_value = raw["render_prim_paths_config"]
        if path_value is None:
            resolved_path = None
        elif isinstance(path_value, str) and path_value.strip():
            resolved_path = _resolve_path(path_value.strip(), base_dir)
        else:
            raise _field_error(
                "front_teeth_only_capture.render_prim_paths_config",
                "a non-empty path string or null",
            )
        if enabled and resolved_path is None:
            raise ValueError(
                "front_teeth_only_capture.render_prim_paths_config is required when "
                "front_teeth_only_capture.enabled is true"
            )
        if not enabled and save_rgb:
            raise ValueError(
                "front_teeth_only_capture.save_rgb must be false when the capture is disabled"
            )
        return cls(
            enabled=enabled,
            render_prim_paths_config=resolved_path,
            save_rgb=save_rgb,
        )


@dataclass(frozen=True)
class VariantTransitionConfig:
    """Render barrier policy applied after motion and visibility changes."""

    settle_render_count: int
    settle_rt_subframes: int
    maximum_settle_attempts: int
    restore_full_scene_after_each_frame: bool

    @classmethod
    def default(cls) -> "VariantTransitionConfig":
        return cls(
            settle_render_count=1,
            settle_rt_subframes=16,
            maximum_settle_attempts=3,
            restore_full_scene_after_each_frame=True,
        )

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "VariantTransitionConfig":
        expected = {
            "settle_render_count",
            "settle_rt_subframes",
            "maximum_settle_attempts",
            "restore_full_scene_after_each_frame",
        }
        unknown = sorted(set(raw) - expected)
        missing = sorted(expected - set(raw))
        if unknown:
            raise ValueError("Unknown variant_transition field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError("Missing variant_transition field(s): " + ", ".join(missing))
        restore = _require_bool(raw, "restore_full_scene_after_each_frame")
        if not restore:
            raise ValueError(
                "variant_transition.restore_full_scene_after_each_frame must be true"
            )
        return cls(
            settle_render_count=_require_integer(
                raw, "settle_render_count", minimum=1
            ),
            settle_rt_subframes=_require_integer(
                raw, "settle_rt_subframes", minimum=1
            ),
            maximum_settle_attempts=_require_integer(
                raw, "maximum_settle_attempts", minimum=1
            ),
            restore_full_scene_after_each_frame=restore,
        )


@dataclass(frozen=True)
class SemanticContentRule:
    """Configuration-owned semantic acceptance rule for one scene variant."""

    allowed_labels: tuple[str, ...] | None
    required_any_labels: tuple[str, ...]
    forbidden_labels: tuple[str, ...]
    allow_empty_target: bool

    @classmethod
    def disabled(cls) -> "SemanticContentRule":
        return cls(
            allowed_labels=None,
            required_any_labels=(),
            forbidden_labels=(),
            allow_empty_target=True,
        )

    @classmethod
    def load(cls, raw: dict[str, Any], field_name: str) -> "SemanticContentRule":
        expected = {
            "allowed_labels",
            "required_any_labels",
            "forbidden_labels",
            "allow_empty_target",
        }
        unknown = sorted(set(raw) - expected)
        missing = sorted(expected - set(raw))
        if unknown:
            raise ValueError(f"Unknown {field_name} field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError(f"Missing {field_name} field(s): " + ", ".join(missing))
        rule = cls(
            allowed_labels=_require_string_tuple(
                raw, "allowed_labels", nullable=True
            ),
            required_any_labels=_require_string_tuple(raw, "required_any_labels"),
            forbidden_labels=_require_string_tuple(raw, "forbidden_labels"),
            allow_empty_target=_require_bool(raw, "allow_empty_target"),
        )
        allowed = (
            {label.casefold() for label in rule.allowed_labels}
            if rule.allowed_labels is not None
            else None
        )
        required = {label.casefold() for label in rule.required_any_labels}
        forbidden = {label.casefold() for label in rule.forbidden_labels}
        overlap = required & forbidden
        if overlap:
            raise ValueError(
                f"{field_name} labels cannot be both required and forbidden: "
                + ", ".join(sorted(overlap))
            )
        if allowed is not None and not required.issubset(allowed):
            raise ValueError(
                f"{field_name}.required_any_labels must be contained in allowed_labels"
            )
        return rule


@dataclass(frozen=True)
class VariantValidationConfig:
    """Semantic-content checks used for both PROBE and formal captures."""

    enabled: bool
    full_scene: SemanticContentRule
    excavator_only: SemanticContentRule
    front_teeth_only: SemanticContentRule

    @classmethod
    def default(cls) -> "VariantValidationConfig":
        disabled = SemanticContentRule.disabled()
        return cls(
            enabled=False,
            full_scene=disabled,
            excavator_only=disabled,
            front_teeth_only=disabled,
        )

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "VariantValidationConfig":
        expected = {"enabled", "full_scene", "excavator_only", "front_teeth_only"}
        unknown = sorted(set(raw) - expected)
        missing = sorted(expected - set(raw))
        if unknown:
            raise ValueError("Unknown variant_validation field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError("Missing variant_validation field(s): " + ", ".join(missing))
        return cls(
            enabled=_require_bool(raw, "enabled"),
            full_scene=SemanticContentRule.load(
                _require_object(raw, "full_scene"), "variant_validation.full_scene"
            ),
            excavator_only=SemanticContentRule.load(
                _require_object(raw, "excavator_only"),
                "variant_validation.excavator_only",
            ),
            front_teeth_only=SemanticContentRule.load(
                _require_object(raw, "front_teeth_only"),
                "variant_validation.front_teeth_only",
            ),
        )

    def rule_for(self, variant: str) -> SemanticContentRule:
        if variant == "full_scene":
            return self.full_scene
        if variant == "excavator_only":
            return self.excavator_only
        if variant == "front_teeth_only":
            return self.front_teeth_only
        raise ValueError(f"Unsupported capture variant: {variant!r}")


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
    image_output_folders: ImageOutputFolders
    excavator_only_capture: ExcavatorOnlyCaptureConfig
    front_teeth_only_capture: FrontTeethOnlyCaptureConfig
    variant_transition: VariantTransitionConfig
    variant_validation: VariantValidationConfig
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
        raw_schema_version = raw.get("schema_version")
        required_fields = (
            _CONFIG_FIELDS
            if raw_schema_version == CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSION
            else _VERSION_3_FIELDS
        )
        missing_fields = sorted(required_fields - actual_fields)
        if missing_fields:
            raise ValueError(
                f"Missing capture configuration field(s): {', '.join(missing_fields)}"
            )

        schema_version = _require_integer(raw, "schema_version", minimum=1)
        if schema_version not in SUPPORTED_CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported capture configuration schema version: {schema_version}; "
                "expected one of "
                f"{SUPPORTED_CAPTURE_LAUNCH_CONFIG_SCHEMA_VERSIONS}"
            )
        if schema_version == 3 and actual_fields & _VERSION_4_FIELDS:
            raise ValueError(
                "Schema-v3 capture configuration cannot contain schema-v4 fields: "
                + ", ".join(sorted(actual_fields & _VERSION_4_FIELDS))
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
        image_output_folders = ImageOutputFolders.load(
            _require_object(raw, "image_output_folders")
        )
        excavator_only_capture = ExcavatorOnlyCaptureConfig.load(
            _require_object(raw, "excavator_only_capture"),
            base_dir=base_dir,
        )
        front_teeth_only_capture = FrontTeethOnlyCaptureConfig.load(
            _require_object(raw, "front_teeth_only_capture"),
            base_dir=base_dir,
        )
        if schema_version == 3 and front_teeth_only_capture.enabled:
            raise ValueError(
                "front_teeth_only_capture requires schema_version 4 so that "
                "variant transition and semantic validation rules are explicit"
            )
        variant_transition = (
            VariantTransitionConfig.load(_require_object(raw, "variant_transition"))
            if schema_version >= 4
            else VariantTransitionConfig.default()
        )
        variant_validation = (
            VariantValidationConfig.load(_require_object(raw, "variant_validation"))
            if schema_version >= 4
            else VariantValidationConfig.default()
        )
        if front_teeth_only_capture.enabled:
            if not variant_validation.enabled:
                raise ValueError(
                    "front_teeth_only_capture requires variant_validation.enabled=true"
                )
            if not variant_validation.full_scene.required_any_labels:
                raise ValueError(
                    "front_teeth_only_capture requires non-empty "
                    "variant_validation.full_scene.required_any_labels"
                )
            if (
                variant_validation.front_teeth_only.allowed_labels is None
                or not variant_validation.front_teeth_only.allowed_labels
            ):
                raise ValueError(
                    "front_teeth_only_capture requires non-empty "
                    "variant_validation.front_teeth_only.allowed_labels"
                )
            if not variant_validation.front_teeth_only.required_any_labels:
                raise ValueError(
                    "front_teeth_only_capture requires non-empty "
                    "variant_validation.front_teeth_only.required_any_labels"
                )
            if (
                excavator_only_capture.enabled
                and not variant_validation.excavator_only.required_any_labels
            ):
                raise ValueError(
                    "front_teeth_only_capture with excavator_only_capture requires "
                    "non-empty variant_validation.excavator_only.required_any_labels"
                )

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
            image_output_folders=image_output_folders,
            excavator_only_capture=excavator_only_capture,
            front_teeth_only_capture=front_teeth_only_capture,
            variant_transition=variant_transition,
            variant_validation=variant_validation,
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
