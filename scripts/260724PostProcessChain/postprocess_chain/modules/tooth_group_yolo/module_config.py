from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ...common.config_io import (
    load_json_object,
    optional_integer,
    optional_string,
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
class EndpointSelector:
    selector_type: str
    labels: Tuple[str, ...]


@dataclass(frozen=True)
class ToothGroupYoloConfig:
    source_artifact: str
    output: ModuleOutputConfig
    yolo_id: int
    yolo_name: str
    endpoint_selector: EndpointSelector
    min_pixels: int
    missing_policy: str


def load_module_config(
    spec: ModuleSpec,
    run_context: RunContext,
) -> ToothGroupYoloConfig:
    raw = load_json_object(spec.config_path, f"module {spec.module_id}")
    context = f"module {spec.module_id}"
    reject_unknown_fields(
        raw,
        {
            "schema_version",
            "source_artifact",
            "output",
            "class",
            "endpoint_selector",
            "min_pixels",
            "missing_policy",
        },
        context,
    )
    if raw.get("schema_version") != 1:
        raise ValueError(f"{context}.schema_version must be 1")

    output = parse_module_output(
        require_object(raw, "output", context),
        f"{context}.output",
        run_context.output_root,
    )
    class_raw = require_object(raw, "class", context)
    reject_unknown_fields(
        class_raw,
        {"yolo_id", "yolo_name"},
        f"{context}.class",
    )
    yolo_id = require_integer(
        class_raw,
        "yolo_id",
        f"{context}.class",
        minimum=0,
    )
    if yolo_id != 0:
        raise ValueError(f"{context}.class.yolo_id must be 0 for a single-class output")
    yolo_name = require_string(class_raw, "yolo_name", f"{context}.class")

    selector_raw = require_object(raw, "endpoint_selector", context)
    reject_unknown_fields(
        selector_raw,
        {"type", "labels"},
        f"{context}.endpoint_selector",
    )
    selector_type = require_string(
        selector_raw,
        "type",
        f"{context}.endpoint_selector",
    )
    if selector_type not in {"semantic_labels", "image_extrema"}:
        raise ValueError(
            f"{context}.endpoint_selector.type must be semantic_labels or image_extrema"
        )
    labels_raw = require_list(
        selector_raw,
        "labels",
        f"{context}.endpoint_selector",
    )
    labels = []
    for index, value in enumerate(labels_raw):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{context}.endpoint_selector.labels[{index}] "
                "must be a non-empty string"
            )
        labels.append(value.strip())
    if len(set(labels)) != len(labels):
        raise ValueError(f"{context}.endpoint_selector.labels contains duplicates")
    if selector_type == "semantic_labels" and len(labels) != 2:
        raise ValueError(
            f"{context}.endpoint_selector.labels must contain exactly two labels "
            "for semantic_labels"
        )
    if selector_type == "image_extrema" and len(labels) < 2:
        raise ValueError(
            f"{context}.endpoint_selector.labels must contain at least two labels "
            "for image_extrema"
        )

    missing_policy = optional_string(
        raw,
        "missing_policy",
        "exclude_frame",
        context,
    )
    if missing_policy not in {
        "exclude_frame",
        "empty_label",
        "error",
        "visible_extrema",
    }:
        raise ValueError(
            f"{context}.missing_policy must be exclude_frame, empty_label, "
            "error, or visible_extrema"
        )

    return ToothGroupYoloConfig(
        source_artifact=require_string(raw, "source_artifact", context),
        output=output,
        yolo_id=yolo_id,
        yolo_name=yolo_name,
        endpoint_selector=EndpointSelector(
            selector_type=selector_type,
            labels=tuple(labels),
        ),
        min_pixels=optional_integer(
            raw,
            "min_pixels",
            10,
            context,
            minimum=1,
        ),
        missing_policy=missing_policy,
    )
