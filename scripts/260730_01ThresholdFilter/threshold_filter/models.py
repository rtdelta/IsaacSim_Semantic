from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class RatioMatrix:
    frame_ids: Tuple[str, ...]
    labels: Tuple[str, ...]
    whole_counts: np.ndarray
    reference_counts: np.ndarray
    ratios: np.ndarray
    statuses: np.ndarray
    source_backend: str

    def __post_init__(self) -> None:
        expected = (len(self.frame_ids), len(self.labels))
        for name, value in (
            ("whole_counts", self.whole_counts),
            ("reference_counts", self.reference_counts),
            ("ratios", self.ratios),
            ("statuses", self.statuses),
        ):
            if value.shape != expected:
                raise ValueError(
                    f"{name} must have shape {expected}, got {value.shape}"
                )
        if len(set(self.frame_ids)) != len(self.frame_ids):
            raise ValueError("ratio matrix contains duplicate frame IDs")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("ratio matrix contains duplicate labels")

    @property
    def frame_to_index(self) -> Dict[str, int]:
        return {frame_id: index for index, frame_id in enumerate(self.frame_ids)}


@dataclass(frozen=True)
class RuleMasks:
    single_drop: np.ndarray
    group_low: np.ndarray
    group_low_counts: np.ndarray
    group_drop: np.ndarray
    legacy_eligible: np.ndarray
    quarantine_frames: np.ndarray

    def __post_init__(self) -> None:
        if self.single_drop.ndim != 2 or self.single_drop.shape[1] != 5:
            raise ValueError("single_drop must have shape [frames, 5]")
        frames = self.single_drop.shape[0]
        if self.group_low.shape != self.single_drop.shape:
            raise ValueError("group_low shape must match single_drop")
        if self.legacy_eligible.shape != self.single_drop.shape:
            raise ValueError("legacy_eligible shape must match single_drop")
        for name, value in (
            ("group_low_counts", self.group_low_counts),
            ("group_drop", self.group_drop),
            ("quarantine_frames", self.quarantine_frames),
        ):
            if value.shape != (frames,):
                raise ValueError(f"{name} must have shape ({frames},)")


@dataclass(frozen=True)
class YoloAnnotation:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float
    raw_line: str
    line_number: int


@dataclass(frozen=True)
class ResolvedToothAnnotation:
    semantic_label: str
    target_index: int
    annotation: YoloAnnotation


@dataclass(frozen=True)
class ModuleFileIndex:
    labels: Mapping[str, Path]
    images: Mapping[str, Path]
    classes_path: Path


@dataclass(frozen=True)
class FileIndex:
    tooth: ModuleFileIndex
    group: ModuleFileIndex


@dataclass(frozen=True)
class InputContract:
    postprocess_manifest: Mapping[str, object]
    ratio_manifest: Mapping[str, object]
    postprocess_manifest_path: Path
    ratio_manifest_path: Path
    tooth_module_dir: Path
    group_module_dir: Path
    ratio_data_path: Path
    input_fingerprint: str
    config_fingerprint: str


@dataclass(frozen=True)
class ToothDecision:
    frame_id: str
    semantic_label: str
    target_index: int
    source_present: bool
    source_class_id: Optional[int]
    source_line_number: Optional[int]
    whole_pixels: int
    reference_pixels: int
    ratio: Optional[float]
    ratio_status: str
    threshold: float
    action: str
    reason: str


@dataclass(frozen=True)
class GroupDecision:
    frame_id: str
    ratios: Tuple[Optional[float], ...]
    statuses: Tuple[str, ...]
    threshold: float
    low_count: int
    minimum_low_teeth: int
    source_present: bool
    action: str
    reason: str


@dataclass(frozen=True)
class FrameResult:
    ordinal: int
    frame_id: str
    tooth_decisions: Tuple[ToothDecision, ...]
    group_decision: GroupDecision
    tooth_source_boxes: int
    tooth_kept_boxes: int
    tooth_dropped_boxes: int
    group_source_boxes: int
    group_kept_boxes: int
    group_dropped_boxes: int
    tooth_output_text: Optional[str]
    group_output_text: Optional[str]
    tooth_label_name: str
    group_label_name: Optional[str]
    anomalies: Tuple[Mapping[str, object], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunSummary:
    values: Mapping[str, object]
