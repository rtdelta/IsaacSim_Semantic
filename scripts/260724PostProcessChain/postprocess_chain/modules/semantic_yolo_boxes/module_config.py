from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from ...common.config_io import (
    load_json_object,
    optional_integer,
    parse_module_output,
    reject_unknown_fields,
    require_integer,
    require_list,
    require_object,
    require_string,
)
from ...common.models import ModuleOutputConfig
from ...pipeline.module_base import RunContext
from ...pipeline.orchestrator_config import ModuleSpec


@dataclass(frozen=True)
class ResolvedTarget:
    yolo_id: int
    yolo_name: str
    semantic_labels: Tuple[str, ...]
    semantic_ids: Tuple[int, ...]


@dataclass(frozen=True)
class SemanticYoloBoxesConfig:
    output: ModuleOutputConfig
    min_pixels: int
    targets: Tuple[ResolvedTarget, ...]

    @property
    def class_names(self) -> Tuple[str, ...]:
        return tuple(target.yolo_name for target in self.targets)

    @property
    def labels_to_ids(self) -> Dict[str, int]:
        return {
            label: semantic_id
            for target in self.targets
            for label, semantic_id in zip(
                target.semantic_labels,
                target.semantic_ids,
            )
        }


def load_module_config(
    spec: ModuleSpec,
    run_context: RunContext,
) -> SemanticYoloBoxesConfig:
    raw = load_json_object(spec.config_path, f"module {spec.module_id}")
    context = f"module {spec.module_id}"
    reject_unknown_fields(
        raw,
        {"schema_version", "output", "min_pixels", "targets"},
        context,
    )
    if raw.get("schema_version") != 1:
        raise ValueError(f"{context}.schema_version must be 1")

    output = parse_module_output(
        require_object(raw, "output", context),
        f"{context}.output",
        run_context.output_root,
    )
    min_pixels = optional_integer(
        raw,
        "min_pixels",
        10,
        context,
        minimum=1,
    )
    raw_targets = require_list(raw, "targets", context)
    if not raw_targets:
        raise ValueError(f"{context}.targets must not be empty")

    by_id: Dict[int, ResolvedTarget] = {}
    used_names = set()
    used_labels = set()
    for index, item in enumerate(raw_targets):
        target_context = f"{context}.targets[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{target_context} must be a JSON object")
        reject_unknown_fields(
            item,
            {"yolo_id", "yolo_name", "semantic_labels"},
            target_context,
        )
        yolo_id = require_integer(
            item,
            "yolo_id",
            target_context,
            minimum=0,
        )
        if yolo_id in by_id:
            raise ValueError(f"{context} contains duplicate yolo_id {yolo_id}")
        yolo_name = require_string(item, "yolo_name", target_context)
        if yolo_name in used_names:
            raise ValueError(f"{context} contains duplicate yolo_name {yolo_name!r}")
        used_names.add(yolo_name)

        labels_raw = require_list(item, "semantic_labels", target_context)
        if not labels_raw:
            raise ValueError(f"{target_context}.semantic_labels must not be empty")
        labels = []
        semantic_ids = []
        for label_index, value in enumerate(labels_raw):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{target_context}.semantic_labels[{label_index}] "
                    "must be a non-empty string"
                )
            label = value.strip()
            if label in used_labels:
                raise ValueError(
                    f"semantic label {label!r} is assigned more than once in {context}"
                )
            try:
                semantic_id = run_context.label_to_id[label]
            except KeyError as exc:
                raise ValueError(
                    f"semantic label {label!r} from {context} is absent from mapping"
                ) from exc
            used_labels.add(label)
            labels.append(label)
            semantic_ids.append(semantic_id)

        by_id[yolo_id] = ResolvedTarget(
            yolo_id=yolo_id,
            yolo_name=yolo_name,
            semantic_labels=tuple(labels),
            semantic_ids=tuple(semantic_ids),
        )

    expected_ids = list(range(len(raw_targets)))
    actual_ids = sorted(by_id)
    if actual_ids != expected_ids:
        raise ValueError(
            f"{context} yolo_id values must be contiguous from 0; "
            f"expected {expected_ids}, got {actual_ids}"
        )
    return SemanticYoloBoxesConfig(
        output=output,
        min_pixels=min_pixels,
        targets=tuple(by_id[yolo_id] for yolo_id in expected_ids),
    )
