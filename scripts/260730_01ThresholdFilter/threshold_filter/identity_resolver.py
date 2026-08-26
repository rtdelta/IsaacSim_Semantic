from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Mapping, Sequence, Tuple

import numpy as np

from .config import RunConfig
from .models import ResolvedToothAnnotation, YoloAnnotation


class AnnotationIdentityResolver(ABC):
    @abstractmethod
    def resolve(
        self,
        annotations: Sequence[YoloAnnotation],
        legacy_eligible: np.ndarray,
    ) -> Tuple[ResolvedToothAnnotation, ...]:
        raise NotImplementedError


class LegacyZeroClassOrderResolver(AnnotationIdentityResolver):
    def __init__(
        self,
        labels: Tuple[str, ...],
        source_class_id: int,
    ) -> None:
        self.labels = labels
        self.source_class_id = source_class_id

    def resolve(
        self,
        annotations: Sequence[YoloAnnotation],
        legacy_eligible: np.ndarray,
    ) -> Tuple[ResolvedToothAnnotation, ...]:
        if legacy_eligible.shape != (len(self.labels),):
            raise ValueError(
                "legacy eligible mask must have one value per physical tooth"
            )
        for annotation in annotations:
            if annotation.class_id != self.source_class_id:
                raise ValueError(
                    "legacy_zero_class_order expected class ID "
                    f"{self.source_class_id}, got {annotation.class_id} "
                    f"on source line {annotation.line_number}"
                )
        expected = [
            (index, label)
            for index, label in enumerate(self.labels)
            if bool(legacy_eligible[index])
        ]
        if len(expected) != len(annotations):
            raise ValueError(
                "legacy_zero_class_order annotation count mismatch: "
                f"expected {len(expected)} from whole_pixels/min_pixels, "
                f"got {len(annotations)}"
            )
        return tuple(
            ResolvedToothAnnotation(
                semantic_label=label,
                target_index=target_index,
                annotation=annotation,
            )
            for (target_index, label), annotation in zip(expected, annotations)
        )


class ClassIdMapResolver(AnnotationIdentityResolver):
    def __init__(
        self,
        labels: Tuple[str, ...],
        mapping: Mapping[int, str],
    ) -> None:
        self.mapping = dict(mapping)
        self.target_index_by_label = {
            label: index for index, label in enumerate(labels)
        }

    def resolve(
        self,
        annotations: Sequence[YoloAnnotation],
        legacy_eligible: np.ndarray,
    ) -> Tuple[ResolvedToothAnnotation, ...]:
        del legacy_eligible
        resolved = []
        used_labels: Dict[str, int] = {}
        for annotation in annotations:
            try:
                label = self.mapping[annotation.class_id]
            except KeyError as exc:
                raise ValueError(
                    f"unknown tooth class ID {annotation.class_id} on "
                    f"source line {annotation.line_number}"
                ) from exc
            if label in used_labels:
                raise ValueError(
                    f"duplicate tooth {label!r} on source lines "
                    f"{used_labels[label]} and {annotation.line_number}"
                )
            used_labels[label] = annotation.line_number
            resolved.append(
                ResolvedToothAnnotation(
                    semantic_label=label,
                    target_index=self.target_index_by_label[label],
                    annotation=annotation,
                )
            )
        return tuple(resolved)


def create_identity_resolver(config: RunConfig) -> AnnotationIdentityResolver:
    labels = config.targets.labels_in_physical_order
    if config.identity.mode == "legacy_zero_class_order":
        return LegacyZeroClassOrderResolver(
            labels=labels,
            source_class_id=(
                config.identity.legacy_zero_class_order.source_class_id
            ),
        )
    if config.identity.mode == "class_id_map":
        return ClassIdMapResolver(
            labels=labels,
            mapping=config.identity.class_id_map.mapping,
        )
    raise ValueError(f"unsupported identity mode: {config.identity.mode}")
