"""Pure semantic-content validation shared by PROBE and formal capture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from capture_context import CaptureVariant
from capture_launch_config import VariantValidationConfig


@dataclass(frozen=True)
class SemanticContentValidationResult:
    dataset_ids_present: tuple[int, ...]
    labels_present: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


def validate_semantic_content(
    *,
    config: VariantValidationConfig,
    variant: CaptureVariant,
    dataset_ids: np.ndarray,
    id_to_label: Mapping[int, str],
    background_id: int,
) -> SemanticContentValidationResult:
    present_ids = tuple(
        int(value)
        for value in np.unique(dataset_ids)
        if int(value) != int(background_id)
    )
    present_labels = tuple(
        id_to_label.get(dataset_id, f"<dataset-id:{dataset_id}>")
        for dataset_id in present_ids
    )
    if not config.enabled:
        return SemanticContentValidationResult(present_ids, present_labels, ())

    rule = config.rule_for(CaptureVariant(variant).value)
    present = {label.casefold() for label in present_labels}
    errors: list[str] = []
    if rule.allowed_labels is not None:
        allowed = {label.casefold() for label in rule.allowed_labels}
        unexpected = sorted(present - allowed)
        if unexpected:
            errors.append("unexpected labels: " + ", ".join(unexpected))

    forbidden = {label.casefold() for label in rule.forbidden_labels}
    forbidden_present = sorted(present & forbidden)
    if forbidden_present:
        errors.append("forbidden labels: " + ", ".join(forbidden_present))

    required = {label.casefold() for label in rule.required_any_labels}
    if required and not (present & required):
        empty_is_allowed = rule.allow_empty_target and not present
        if not empty_is_allowed:
            errors.append(
                "none of required_any_labels are visible: "
                + ", ".join(rule.required_any_labels)
            )

    return SemanticContentValidationResult(
        dataset_ids_present=present_ids,
        labels_present=present_labels,
        errors=tuple(errors),
    )
