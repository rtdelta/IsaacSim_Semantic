from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from .models import CollisionClassSpec, TargetSpec
from .modules.component_filter.config import ComponentFilterConfig
from .modules.collision_box.config import CollisionBoxConfig
from .modules.pose_metrics.config import PoseMetricsConfig
from .modules.semantic_features.config import SemanticFeaturesConfig
from .modules.single_tooth_boxes.config import SingleToothBoxesConfig
from .modules.threshold_rules.config import (
    CollisionRuleConfig,
    SingleToothRuleConfig,
    ThresholdRulesConfig,
)
from .modules.visibility_ratio.config import VisibilityRatioConfig


def _load_object(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"cannot read config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("config must contain a JSON object")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], context: str) -> None:
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


def _boolean(value: Mapping[str, Any], key: str, context: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return item


def _integer(
    value: Mapping[str, Any],
    key: str,
    context: str,
    minimum: int = 0,
) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{context}.{key} must be an integer >= {minimum}")
    return item


def _number(
    value: Mapping[str, Any],
    key: str,
    context: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ValueError(f"{context}.{key} must be a number")
    result = float(item)
    if minimum is not None and result < minimum:
        raise ValueError(f"{context}.{key} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{context}.{key} must be <= {maximum}")
    return result


def _choice(
    value: Mapping[str, Any],
    key: str,
    context: str,
    choices: set[str],
) -> str:
    item = _string(value, key, context)
    if item not in choices:
        raise ValueError(
            f"{context}.{key} must be one of: {', '.join(sorted(choices))}"
        )
    return item


def _resolve(base: Path, text: str) -> Path:
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


@dataclass(frozen=True)
class PipelineConfig:
    mode: str
    strict_pairing: bool
    on_frame_error: str


@dataclass(frozen=True)
class FullSceneInputConfig:
    rgb_dir: Path
    semantic_dir: Path


@dataclass(frozen=True)
class ReferenceInputConfig:
    capture_variant: str
    semantic_dir: Path


@dataclass(frozen=True)
class InputsConfig:
    full_scene: FullSceneInputConfig
    reference: ReferenceInputConfig
    semantic_mapping: Path


@dataclass(frozen=True)
class TargetsConfig:
    teeth: Tuple[TargetSpec, ...]
    collision_model: CollisionClassSpec


@dataclass(frozen=True)
class ModulesConfig:
    semantic_features: SemanticFeaturesConfig
    component_filter: ComponentFilterConfig
    visibility_ratio: VisibilityRatioConfig
    pose_metrics: PoseMetricsConfig
    single_tooth_boxes: SingleToothBoxesConfig
    threshold_rules: ThresholdRulesConfig
    collision_box: CollisionBoxConfig


@dataclass(frozen=True)
class ExecutionConfig:
    backend: str
    workers: int
    max_in_flight: int
    reader_threads: int
    verification_level: str
    verification_sample_frames: int


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool
    reuse: bool
    directory: Path
    fingerprint_mode: str
    on_mismatch: str


@dataclass(frozen=True)
class OutputConfig:
    root: Path
    overwrite: bool
    image_mode: str
    keep_empty_label_files: bool
    staging_mode: str


@dataclass(frozen=True)
class ReportingConfig:
    level: str


@dataclass(frozen=True)
class RunConfig:
    config_path: Path
    pipeline: PipelineConfig
    inputs: InputsConfig
    targets: TargetsConfig
    modules: ModulesConfig
    execution: ExecutionConfig
    cache: CacheConfig
    output: OutputConfig
    reporting: ReportingConfig


def _load_pipeline(raw: Mapping[str, Any]) -> PipelineConfig:
    context = "config.pipeline"
    _reject_unknown(raw, {"mode", "strict_pairing", "on_frame_error"}, context)
    mode = _choice(raw, "mode", context, {"full", "analyze_only", "filter_only"})
    strict = _boolean(raw, "strict_pairing", context)
    if not strict:
        raise ValueError("config.pipeline.strict_pairing must be true")
    on_error = _choice(raw, "on_frame_error", context, {"fail_fast"})
    return PipelineConfig(mode=mode, strict_pairing=strict, on_frame_error=on_error)


def _load_inputs(raw: Mapping[str, Any], base: Path) -> InputsConfig:
    context = "config.inputs"
    _reject_unknown(raw, {"full_scene", "reference", "semantic_mapping"}, context)
    full = _object(raw, "full_scene", context)
    reference = _object(raw, "reference", context)
    _reject_unknown(full, {"rgb_dir", "semantic_dir"}, f"{context}.full_scene")
    _reject_unknown(
        reference,
        {"capture_variant", "semantic_dir"},
        f"{context}.reference",
    )
    return InputsConfig(
        full_scene=FullSceneInputConfig(
            rgb_dir=_resolve(base, _string(full, "rgb_dir", f"{context}.full_scene")),
            semantic_dir=_resolve(
                base, _string(full, "semantic_dir", f"{context}.full_scene")
            ),
        ),
        reference=ReferenceInputConfig(
            capture_variant=_choice(
                reference,
                "capture_variant",
                f"{context}.reference",
                {"front_teeth_only"},
            ),
            semantic_dir=_resolve(
                base,
                _string(reference, "semantic_dir", f"{context}.reference"),
            )
        ),
        semantic_mapping=_resolve(base, _string(raw, "semantic_mapping", context)),
    )


def _load_targets(raw: Mapping[str, Any]) -> TargetsConfig:
    context = "config.targets"
    _reject_unknown(raw, {"teeth", "collision_model"}, context)
    teeth_raw = raw.get("teeth")
    if not isinstance(teeth_raw, list) or len(teeth_raw) != 5:
        raise ValueError("config.targets.teeth must contain exactly five objects")
    teeth = []
    for index, item in enumerate(teeth_raw):
        item_context = f"{context}.teeth[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{item_context} must be an object")
        _reject_unknown(
            item, {"class_id", "class_name", "semantic_label"}, item_context
        )
        teeth.append(
            TargetSpec(
                class_id=_integer(item, "class_id", item_context),
                class_name=_string(item, "class_name", item_context),
                semantic_label=_string(item, "semantic_label", item_context),
            )
        )
    if [item.class_id for item in teeth] != list(range(5)):
        raise ValueError("config.targets.teeth class_id values must be exactly 0..4")
    if len({item.class_name for item in teeth}) != 5:
        raise ValueError("config.targets.teeth class_name values must be unique")
    if len({item.semantic_label for item in teeth}) != 5:
        raise ValueError("config.targets.teeth semantic_label values must be unique")
    collision = _object(raw, "collision_model", context)
    collision_context = f"{context}.collision_model"
    _reject_unknown(collision, {"class_id", "class_name"}, collision_context)
    collision_class = CollisionClassSpec(
        class_id=_integer(collision, "class_id", collision_context),
        class_name=_string(collision, "class_name", collision_context),
    )
    if collision_class.class_id != 0:
        raise ValueError("collision model class_id must be 0")
    return TargetsConfig(teeth=tuple(teeth), collision_model=collision_class)


def _enabled(raw: Mapping[str, Any], context: str) -> bool:
    enabled = _boolean(raw, "enabled", context)
    if not enabled:
        raise ValueError(f"{context}.enabled must be true in schema version 1")
    return enabled


def _load_modules(raw: Mapping[str, Any]) -> ModulesConfig:
    context = "config.modules"
    names = {
        "semantic_features",
        "component_filter",
        "visibility_ratio",
        "pose_metrics",
        "single_tooth_boxes",
        "threshold_rules",
        "collision_box",
    }
    _reject_unknown(raw, names, context)

    semantic = _object(raw, "semantic_features", context)
    semantic_context = f"{context}.semantic_features"
    _reject_unknown(semantic, {"enabled", "target_extraction"}, semantic_context)
    semantic_config = SemanticFeaturesConfig(
        enabled=_enabled(semantic, semantic_context),
        target_extraction=_choice(
            semantic,
            "target_extraction",
            semantic_context,
            {"single_target_scan"},
        ),
    )

    component_filter = _object(raw, "component_filter", context)
    component_filter_context = f"{context}.component_filter"
    _reject_unknown(
        component_filter,
        {"enabled", "connectivity", "minimum_connected_component_pixels"},
        component_filter_context,
    )
    component_filter_config = ComponentFilterConfig(
        enabled=_boolean(component_filter, "enabled", component_filter_context),
        connectivity=_integer(
            component_filter, "connectivity", component_filter_context, 1
        ),
        minimum_connected_component_pixels=_integer(
            component_filter,
            "minimum_connected_component_pixels",
            component_filter_context,
            1,
        ),
    )
    if component_filter_config.connectivity != 4:
        raise ValueError("config.modules.component_filter.connectivity must be 4")

    visibility = _object(raw, "visibility_ratio", context)
    visibility_context = f"{context}.visibility_ratio"
    _reject_unknown(
        visibility,
        {"enabled", "zero_reference_value", "ratio_over_one"},
        visibility_context,
    )
    visibility_config = VisibilityRatioConfig(
        enabled=_enabled(visibility, visibility_context),
        zero_reference_value=_number(
            visibility, "zero_reference_value", visibility_context
        ),
        ratio_over_one=_choice(
            visibility,
            "ratio_over_one",
            visibility_context,
            {"keep_and_flag"},
        ),
    )
    if visibility_config.zero_reference_value != -1.0:
        raise ValueError("zero_reference_value must be -1")

    pose = _object(raw, "pose_metrics", context)
    pose_context = f"{context}.pose_metrics"
    _reject_unknown(
        pose,
        {"enabled", "algorithm", "invalid_value", "write_angle"},
        pose_context,
    )
    pose_config = PoseMetricsConfig(
        enabled=_enabled(pose, pose_context),
        algorithm=_choice(
            pose,
            "algorithm",
            pose_context,
            {"pixel_cell_min_area_rect_v1"},
        ),
        invalid_value=_number(pose, "invalid_value", pose_context),
        write_angle=_boolean(pose, "write_angle", pose_context),
    )
    if pose_config.invalid_value != -1.0:
        raise ValueError("pose_metrics.invalid_value must be -1")

    single_boxes = _object(raw, "single_tooth_boxes", context)
    single_context = f"{context}.single_tooth_boxes"
    _reject_unknown(single_boxes, {"enabled", "minimum_pixels"}, single_context)
    single_boxes_config = SingleToothBoxesConfig(
        enabled=_enabled(single_boxes, single_context),
        minimum_pixels=_integer(single_boxes, "minimum_pixels", single_context, 1),
    )

    rules = _object(raw, "threshold_rules", context)
    rules_context = f"{context}.threshold_rules"
    _reject_unknown(
        rules, {"enabled", "single_tooth", "collision_model"}, rules_context
    )
    _enabled(rules, rules_context)
    single_rules = _object(rules, "single_tooth", rules_context)
    single_rules_context = f"{rules_context}.single_tooth"
    _reject_unknown(
        single_rules,
        {
            "minimum_visible_ratio_a",
            "minimum_fill_ratio_c",
            "height_width_axis_mode",
            "minimum_height_width_ratio_d",
            "drop_all_single_boxes_if_bad_teeth_at_least",
        },
        single_rules_context,
    )
    collision_rules = _object(rules, "collision_model", rules_context)
    collision_rules_context = f"{rules_context}.collision_model"
    _reject_unknown(
        collision_rules,
        {
            "minimum_visible_ratio_b",
            "drop_collision_box_if_bad_teeth_at_least",
        },
        collision_rules_context,
    )
    rule_config = ThresholdRulesConfig(
        enabled=True,
        single_tooth=SingleToothRuleConfig(
            minimum_visible_ratio_a=_number(
                single_rules,
                "minimum_visible_ratio_a",
                single_rules_context,
                0.0,
                1.0,
            ),
            minimum_fill_ratio_c=_number(
                single_rules,
                "minimum_fill_ratio_c",
                single_rules_context,
                0.0,
                1.0,
            ),
            height_width_axis_mode=_choice(
                single_rules,
                "height_width_axis_mode",
                single_rules_context,
                {"x_over_y", "y_over_x"},
            ),
            minimum_height_width_ratio_d=_number(
                single_rules,
                "minimum_height_width_ratio_d",
                single_rules_context,
                0.0,
            ),
            drop_all_single_boxes_if_bad_teeth_at_least=_integer(
                single_rules,
                "drop_all_single_boxes_if_bad_teeth_at_least",
                single_rules_context,
                1,
            ),
        ),
        collision_model=CollisionRuleConfig(
            minimum_visible_ratio_b=_number(
                collision_rules,
                "minimum_visible_ratio_b",
                collision_rules_context,
                0.0,
                1.0,
            ),
            drop_collision_box_if_bad_teeth_at_least=_integer(
                collision_rules,
                "drop_collision_box_if_bad_teeth_at_least",
                collision_rules_context,
                1,
            ),
        ),
    )
    if rule_config.single_tooth.drop_all_single_boxes_if_bad_teeth_at_least > 5:
        raise ValueError("single bad tooth count threshold must be <= 5")
    if rule_config.collision_model.drop_collision_box_if_bad_teeth_at_least > 5:
        raise ValueError("collision bad tooth count threshold must be <= 5")

    collision_box = _object(raw, "collision_box", context)
    collision_box_context = f"{context}.collision_box"
    _reject_unknown(
        collision_box,
        {"enabled", "length_axis", "length_source", "width_source", "union_scope"},
        collision_box_context,
    )
    collision_box_config = CollisionBoxConfig(
        enabled=_enabled(collision_box, collision_box_context),
        length_axis=_choice(
            collision_box, "length_axis", collision_box_context, {"x", "y"}
        ),
        length_source=_choice(
            collision_box,
            "length_source",
            collision_box_context,
            {"full_scene"},
        ),
        width_source=_choice(
            collision_box,
            "width_source",
            collision_box_context,
            {"reference"},
        ),
        union_scope=_choice(
            collision_box,
            "union_scope",
            collision_box_context,
            {"all_valid_teeth"},
        ),
    )
    return ModulesConfig(
        semantic_features=semantic_config,
        component_filter=component_filter_config,
        visibility_ratio=visibility_config,
        pose_metrics=pose_config,
        single_tooth_boxes=single_boxes_config,
        threshold_rules=rule_config,
        collision_box=collision_box_config,
    )


def load_config(path: Path) -> RunConfig:
    path = path.resolve()
    raw = _load_object(path)
    _reject_unknown(
        raw,
        {
            "schema_version",
            "pipeline",
            "inputs",
            "targets",
            "modules",
            "execution",
            "cache",
            "output",
            "reporting",
        },
        "config",
    )
    if raw.get("schema_version") != 2:
        raise ValueError("config.schema_version must be 2")
    base = path.parent
    output_raw = _object(raw, "output", "config")
    _reject_unknown(
        output_raw,
        {
            "root",
            "overwrite",
            "image_mode",
            "keep_empty_label_files",
            "staging_mode",
        },
        "config.output",
    )
    output = OutputConfig(
        root=_resolve(base, _string(output_raw, "root", "config.output")),
        overwrite=_boolean(output_raw, "overwrite", "config.output"),
        image_mode=_choice(
            output_raw,
            "image_mode",
            "config.output",
            {"none", "hardlink_required", "hardlink_or_copy", "copy"},
        ),
        keep_empty_label_files=_boolean(
            output_raw, "keep_empty_label_files", "config.output"
        ),
        staging_mode=_choice(
            output_raw,
            "staging_mode",
            "config.output",
            {"atomic_directory"},
        ),
    )

    execution_raw = _object(raw, "execution", "config")
    _reject_unknown(
        execution_raw,
        {
            "backend",
            "workers",
            "max_in_flight",
            "reader_threads",
            "verification_level",
            "verification_sample_frames",
        },
        "config.execution",
    )
    execution = ExecutionConfig(
        backend=_choice(execution_raw, "backend", "config.execution", {"numpy_opencv"}),
        workers=_integer(execution_raw, "workers", "config.execution", 1),
        max_in_flight=_integer(execution_raw, "max_in_flight", "config.execution", 1),
        reader_threads=_integer(execution_raw, "reader_threads", "config.execution", 1),
        verification_level=_choice(
            execution_raw,
            "verification_level",
            "config.execution",
            {"none", "sample", "full"},
        ),
        verification_sample_frames=_integer(
            execution_raw,
            "verification_sample_frames",
            "config.execution",
            0,
        ),
    )
    if execution.max_in_flight < execution.workers:
        raise ValueError("execution.max_in_flight must be >= workers")

    cache_raw = _object(raw, "cache", "config")
    _reject_unknown(
        cache_raw,
        {"enabled", "reuse", "directory", "fingerprint_mode", "on_mismatch"},
        "config.cache",
    )
    cache = CacheConfig(
        enabled=_boolean(cache_raw, "enabled", "config.cache"),
        reuse=_boolean(cache_raw, "reuse", "config.cache"),
        directory=_resolve(base, _string(cache_raw, "directory", "config.cache")),
        fingerprint_mode=_choice(
            cache_raw,
            "fingerprint_mode",
            "config.cache",
            {"metadata", "content"},
        ),
        on_mismatch=_choice(cache_raw, "on_mismatch", "config.cache", {"rebuild"}),
    )

    reporting_raw = _object(raw, "reporting", "config")
    _reject_unknown(reporting_raw, {"level"}, "config.reporting")
    reporting = ReportingConfig(
        level=_choice(reporting_raw, "level", "config.reporting", {"full"})
    )
    pipeline = _load_pipeline(_object(raw, "pipeline", "config"))
    config = RunConfig(
        config_path=path,
        pipeline=pipeline,
        inputs=_load_inputs(_object(raw, "inputs", "config"), base),
        targets=_load_targets(_object(raw, "targets", "config")),
        modules=_load_modules(_object(raw, "modules", "config")),
        execution=execution,
        cache=cache,
        output=output,
        reporting=reporting,
    )
    if not config.cache.enabled and config.cache.reuse:
        raise ValueError("cache.reuse must be false when cache.enabled=false")
    if config.pipeline.mode == "filter_only" and (
        not config.cache.enabled or not config.cache.reuse
    ):
        raise ValueError(
            "filter_only mode requires cache.enabled=true and cache.reuse=true"
        )
    if config.pipeline.mode != "analyze_only" and config.output.image_mode == "none":
        raise ValueError(
            "full and filter_only modes require RGB output; "
            "output.image_mode cannot be none"
        )
    return config


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def resolved_config_dict(config: RunConfig) -> Dict[str, Any]:
    value = asdict(config)
    value.pop("config_path", None)
    return {"schema_version": 2, **_json_value(value)}
