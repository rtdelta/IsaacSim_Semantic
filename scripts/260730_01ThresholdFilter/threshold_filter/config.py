from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


def _load_object(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"cannot read config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("config must contain a JSON object")
    return value


def _reject_unknown(
    value: Mapping[str, Any],
    allowed: set,
    context: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def _object(value: Mapping[str, Any], key: str, context: str) -> Dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"{context}.{key} must be an object")
    return item


def _string(value: Mapping[str, Any], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return item.strip()


def _integer(
    value: Mapping[str, Any],
    key: str,
    context: str,
    minimum: int,
    default: Any = None,
) -> int:
    item = value.get(key, default)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{context}.{key} must be an integer >= {minimum}")
    return item


def _number(
    value: Mapping[str, Any],
    key: str,
    context: str,
    minimum: float,
    maximum: float,
) -> float:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ValueError(f"{context}.{key} must be a number")
    result = float(item)
    if not minimum <= result <= maximum:
        raise ValueError(
            f"{context}.{key} must be between {minimum} and {maximum}"
        )
    return result


def _boolean(
    value: Mapping[str, Any],
    key: str,
    context: str,
    default: bool,
) -> bool:
    item = value.get(key, default)
    if not isinstance(item, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return item


def _choice(
    value: Mapping[str, Any],
    key: str,
    context: str,
    allowed: set,
) -> str:
    item = _string(value, key, context)
    if item not in allowed:
        raise ValueError(
            f"{context}.{key} must be one of: {', '.join(sorted(allowed))}"
        )
    return item


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _resolve_under(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


@dataclass(frozen=True)
class PostProcessInputConfig:
    output_root: Path
    manifest: Path
    tooth_module_dir: Path
    group_module_dir: Path


@dataclass(frozen=True)
class PixelRatioInputConfig:
    output_root: Path
    manifest: Path
    input_format: str
    counts_cache: Path
    per_frame_csv: Path


@dataclass(frozen=True)
class InputsConfig:
    postprocess: PostProcessInputConfig
    pixel_ratio: PixelRatioInputConfig


@dataclass(frozen=True)
class TargetsConfig:
    labels_in_physical_order: Tuple[str, ...]
    group_name: str


@dataclass(frozen=True)
class LegacyIdentityConfig:
    source_class_id: int
    source_min_pixels: int


@dataclass(frozen=True)
class ClassIdIdentityConfig:
    mapping: Mapping[int, str]


@dataclass(frozen=True)
class IdentityConfig:
    mode: str
    legacy_zero_class_order: LegacyIdentityConfig
    class_id_map: ClassIdIdentityConfig


@dataclass(frozen=True)
class SingleToothRuleConfig:
    minimum_visible_ratio: float


@dataclass(frozen=True)
class ToothGroupRuleConfig:
    minimum_visible_ratio: float
    minimum_low_teeth: int


@dataclass(frozen=True)
class RulesConfig:
    single_tooth: SingleToothRuleConfig
    tooth_group: ToothGroupRuleConfig


@dataclass(frozen=True)
class RatioHandlingConfig:
    reference_missing: str
    empty_ratio: str
    ratio_over_one: str


@dataclass(frozen=True)
class ExecutionConfig:
    workers: int
    max_in_flight: int
    on_error: str
    dry_run: bool
    staging_mode: str


@dataclass(frozen=True)
class PerformanceConfig:
    vectorized_rules: bool
    directory_scan: str
    durability: str
    verification_level: str
    verification_sample_frames: int


@dataclass(frozen=True)
class OutputConfig:
    root: Path
    overwrite: bool
    image_mode: str
    keep_empty_label_files: bool


@dataclass(frozen=True)
class ReportingConfig:
    level: str


@dataclass(frozen=True)
class RunConfig:
    config_path: Path
    inputs: InputsConfig
    targets: TargetsConfig
    identity: IdentityConfig
    rules: RulesConfig
    ratio_handling: RatioHandlingConfig
    execution: ExecutionConfig
    performance: PerformanceConfig
    output: OutputConfig
    reporting: ReportingConfig

    def fingerprint(self) -> str:
        encoded = json.dumps(
            resolved_config_dict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _load_postprocess(
    raw: Mapping[str, Any],
    config_base: Path,
) -> PostProcessInputConfig:
    context = "config.inputs.postprocess"
    _reject_unknown(
        raw,
        {"output_root", "manifest", "tooth_module_dir", "group_module_dir"},
        context,
    )
    root = _resolve(config_base, _string(raw, "output_root", context))
    return PostProcessInputConfig(
        output_root=root,
        manifest=_resolve_under(root, _string(raw, "manifest", context)),
        tooth_module_dir=_resolve_under(
            root, _string(raw, "tooth_module_dir", context)
        ),
        group_module_dir=_resolve_under(
            root, _string(raw, "group_module_dir", context)
        ),
    )


def _load_pixel_ratio(
    raw: Mapping[str, Any],
    config_base: Path,
) -> PixelRatioInputConfig:
    context = "config.inputs.pixel_ratio"
    _reject_unknown(
        raw,
        {
            "output_root",
            "manifest",
            "input_format",
            "counts_cache",
            "per_frame_csv",
        },
        context,
    )
    root = _resolve(config_base, _string(raw, "output_root", context))
    return PixelRatioInputConfig(
        output_root=root,
        manifest=_resolve_under(root, _string(raw, "manifest", context)),
        input_format=_choice(
            raw,
            "input_format",
            context,
            {"counts_cache_npz", "per_frame_csv"},
        ),
        counts_cache=_resolve_under(root, _string(raw, "counts_cache", context)),
        per_frame_csv=_resolve_under(
            root, _string(raw, "per_frame_csv", context)
        ),
    )


def _load_targets(raw: Mapping[str, Any]) -> TargetsConfig:
    context = "config.targets"
    _reject_unknown(raw, {"labels_in_physical_order", "group_name"}, context)
    labels_raw = raw.get("labels_in_physical_order")
    if (
        not isinstance(labels_raw, list)
        or len(labels_raw) != 5
        or not all(isinstance(item, str) and item.strip() for item in labels_raw)
    ):
        raise ValueError(
            "config.targets.labels_in_physical_order must contain exactly "
            "five non-empty strings"
        )
    labels = tuple(item.strip() for item in labels_raw)
    if len(set(labels)) != 5:
        raise ValueError(
            "config.targets.labels_in_physical_order must not contain duplicates"
        )
    group_name = _string(raw, "group_name", context)
    if group_name in labels:
        raise ValueError("config.targets.group_name must differ from tooth labels")
    return TargetsConfig(labels_in_physical_order=labels, group_name=group_name)


def _load_identity(
    raw: Mapping[str, Any],
    targets: TargetsConfig,
) -> IdentityConfig:
    context = "config.identity"
    _reject_unknown(
        raw,
        {"mode", "legacy_zero_class_order", "class_id_map"},
        context,
    )
    mode = _choice(
        raw,
        "mode",
        context,
        {"legacy_zero_class_order", "class_id_map"},
    )

    legacy_raw = _object(raw, "legacy_zero_class_order", context)
    legacy_context = f"{context}.legacy_zero_class_order"
    _reject_unknown(
        legacy_raw,
        {"source_class_id", "source_min_pixels"},
        legacy_context,
    )
    legacy = LegacyIdentityConfig(
        source_class_id=_integer(
            legacy_raw, "source_class_id", legacy_context, minimum=0
        ),
        source_min_pixels=_integer(
            legacy_raw, "source_min_pixels", legacy_context, minimum=1
        ),
    )

    class_raw = _object(raw, "class_id_map", context)
    class_context = f"{context}.class_id_map"
    _reject_unknown(class_raw, {"mapping"}, class_context)
    mapping_raw = class_raw.get("mapping")
    if not isinstance(mapping_raw, dict) or not mapping_raw:
        raise ValueError(f"{class_context}.mapping must be a non-empty object")
    mapping: Dict[int, str] = {}
    for raw_id, raw_label in mapping_raw.items():
        try:
            class_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{class_context}.mapping key must be an integer: {raw_id!r}"
            ) from exc
        if str(class_id) != str(raw_id).strip() or class_id < 0:
            raise ValueError(
                f"{class_context}.mapping key must be a non-negative integer: "
                f"{raw_id!r}"
            )
        if not isinstance(raw_label, str) or not raw_label.strip():
            raise ValueError(
                f"{class_context}.mapping[{raw_id!r}] must be a non-empty string"
            )
        mapping[class_id] = raw_label.strip()
    if set(mapping.values()) != set(targets.labels_in_physical_order):
        raise ValueError(
            f"{class_context}.mapping values must exactly cover the five "
            "configured tooth labels"
        )
    if len(set(mapping.values())) != len(mapping):
        raise ValueError(f"{class_context}.mapping contains duplicate labels")

    return IdentityConfig(
        mode=mode,
        legacy_zero_class_order=legacy,
        class_id_map=ClassIdIdentityConfig(mapping=mapping),
    )


def load_config(path: Path) -> RunConfig:
    path = path.resolve()
    raw = _load_object(path)
    _reject_unknown(
        raw,
        {
            "schema_version",
            "inputs",
            "targets",
            "identity",
            "rules",
            "ratio_handling",
            "execution",
            "performance",
            "output",
            "reporting",
        },
        "config",
    )
    if raw.get("schema_version") != 1:
        raise ValueError("config.schema_version must be 1")
    base = path.parent

    inputs_raw = _object(raw, "inputs", "config")
    _reject_unknown(inputs_raw, {"postprocess", "pixel_ratio"}, "config.inputs")
    inputs = InputsConfig(
        postprocess=_load_postprocess(
            _object(inputs_raw, "postprocess", "config.inputs"), base
        ),
        pixel_ratio=_load_pixel_ratio(
            _object(inputs_raw, "pixel_ratio", "config.inputs"), base
        ),
    )
    targets = _load_targets(_object(raw, "targets", "config"))
    identity = _load_identity(_object(raw, "identity", "config"), targets)

    rules_raw = _object(raw, "rules", "config")
    _reject_unknown(rules_raw, {"single_tooth", "tooth_group"}, "config.rules")
    single_raw = _object(rules_raw, "single_tooth", "config.rules")
    _reject_unknown(
        single_raw,
        {"minimum_visible_ratio"},
        "config.rules.single_tooth",
    )
    group_raw = _object(rules_raw, "tooth_group", "config.rules")
    _reject_unknown(
        group_raw,
        {"minimum_visible_ratio", "minimum_low_teeth"},
        "config.rules.tooth_group",
    )
    rules = RulesConfig(
        single_tooth=SingleToothRuleConfig(
            minimum_visible_ratio=_number(
                single_raw,
                "minimum_visible_ratio",
                "config.rules.single_tooth",
                0.0,
                1.0,
            )
        ),
        tooth_group=ToothGroupRuleConfig(
            minimum_visible_ratio=_number(
                group_raw,
                "minimum_visible_ratio",
                "config.rules.tooth_group",
                0.0,
                1.0,
            ),
            minimum_low_teeth=_integer(
                group_raw,
                "minimum_low_teeth",
                "config.rules.tooth_group",
                minimum=1,
            ),
        ),
    )
    if rules.tooth_group.minimum_low_teeth > 5:
        raise ValueError(
            "config.rules.tooth_group.minimum_low_teeth must be <= 5"
        )

    handling_raw = _object(raw, "ratio_handling", "config")
    _reject_unknown(
        handling_raw,
        {"reference_missing", "empty_ratio", "ratio_over_one"},
        "config.ratio_handling",
    )
    invalid_choices = {"error", "keep", "drop", "quarantine"}
    ratio_handling = RatioHandlingConfig(
        reference_missing=_choice(
            handling_raw,
            "reference_missing",
            "config.ratio_handling",
            invalid_choices,
        ),
        empty_ratio=_choice(
            handling_raw,
            "empty_ratio",
            "config.ratio_handling",
            invalid_choices,
        ),
        ratio_over_one=_choice(
            handling_raw,
            "ratio_over_one",
            "config.ratio_handling",
            {"use_raw", "clip", "error"},
        ),
    )

    execution_raw = _object(raw, "execution", "config")
    _reject_unknown(
        execution_raw,
        {
            "workers",
            "max_in_flight",
            "on_error",
            "dry_run",
            "staging_mode",
        },
        "config.execution",
    )
    execution = ExecutionConfig(
        workers=_integer(
            execution_raw, "workers", "config.execution", minimum=1
        ),
        max_in_flight=_integer(
            execution_raw, "max_in_flight", "config.execution", minimum=1
        ),
        on_error=_choice(
            execution_raw,
            "on_error",
            "config.execution",
            {"fail_fast", "continue"},
        ),
        dry_run=_boolean(
            execution_raw, "dry_run", "config.execution", default=False
        ),
        staging_mode=_choice(
            execution_raw,
            "staging_mode",
            "config.execution",
            {"atomic_directory"},
        ),
    )
    if execution.max_in_flight < execution.workers:
        raise ValueError(
            "config.execution.max_in_flight must be >= config.execution.workers"
        )

    performance_raw = _object(raw, "performance", "config")
    _reject_unknown(
        performance_raw,
        {
            "vectorized_rules",
            "directory_scan",
            "durability",
            "verification_level",
            "verification_sample_frames",
        },
        "config.performance",
    )
    performance = PerformanceConfig(
        vectorized_rules=_boolean(
            performance_raw,
            "vectorized_rules",
            "config.performance",
            default=True,
        ),
        directory_scan=_choice(
            performance_raw,
            "directory_scan",
            "config.performance",
            {"single_pass"},
        ),
        durability=_choice(
            performance_raw,
            "durability",
            "config.performance",
            {"run_level"},
        ),
        verification_level=_choice(
            performance_raw,
            "verification_level",
            "config.performance",
            {"none", "sample", "full"},
        ),
        verification_sample_frames=_integer(
            performance_raw,
            "verification_sample_frames",
            "config.performance",
            minimum=0,
        ),
    )
    if not performance.vectorized_rules:
        raise ValueError(
            "config.performance.vectorized_rules must be true in schema version 1"
        )

    output_raw = _object(raw, "output", "config")
    _reject_unknown(
        output_raw,
        {"root", "overwrite", "image_mode", "keep_empty_label_files"},
        "config.output",
    )
    output = OutputConfig(
        root=_resolve(base, _string(output_raw, "root", "config.output")),
        overwrite=_boolean(
            output_raw, "overwrite", "config.output", default=False
        ),
        image_mode=_choice(
            output_raw,
            "image_mode",
            "config.output",
            {"none", "hardlink_required", "hardlink_or_copy", "symlink", "copy"},
        ),
        keep_empty_label_files=_boolean(
            output_raw,
            "keep_empty_label_files",
            "config.output",
            default=True,
        ),
    )

    reporting_raw = _object(raw, "reporting", "config")
    _reject_unknown(reporting_raw, {"level"}, "config.reporting")
    reporting = ReportingConfig(
        level=_choice(
            reporting_raw,
            "level",
            "config.reporting",
            {"summary", "full"},
        )
    )

    config = RunConfig(
        config_path=path,
        inputs=inputs,
        targets=targets,
        identity=identity,
        rules=rules,
        ratio_handling=ratio_handling,
        execution=execution,
        performance=performance,
        output=output,
        reporting=reporting,
    )
    _validate_path_separation(config)
    return config


def _validate_path_separation(config: RunConfig) -> None:
    output = config.output.root
    for input_root in (
        config.inputs.postprocess.output_root,
        config.inputs.pixel_ratio.output_root,
    ):
        if (
            output == input_root
            or input_root in output.parents
            or output in input_root.parents
        ):
            raise ValueError(
                "output root must not equal, contain, or be contained by "
                f"input root: {input_root}"
            )


def resolved_config_dict(config: RunConfig) -> Dict[str, Any]:
    value = asdict(config)

    def convert(item: Any) -> Any:
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, dict):
            return {str(key): convert(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(child) for child in item]
        return item

    return convert(value)


__all__ = [
    "ClassIdIdentityConfig",
    "ExecutionConfig",
    "IdentityConfig",
    "InputsConfig",
    "LegacyIdentityConfig",
    "OutputConfig",
    "PerformanceConfig",
    "PixelRatioInputConfig",
    "PostProcessInputConfig",
    "RatioHandlingConfig",
    "ReportingConfig",
    "RulesConfig",
    "RunConfig",
    "TargetsConfig",
    "load_config",
    "resolved_config_dict",
]
