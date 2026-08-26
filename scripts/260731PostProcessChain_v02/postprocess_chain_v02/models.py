from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple

import numpy as np

from .common.pixel_box import PixelBox


@dataclass(frozen=True)
class TargetSpec:
    class_id: int
    class_name: str
    semantic_label: str


@dataclass(frozen=True)
class CollisionClassSpec:
    class_id: int
    class_name: str


@dataclass(frozen=True)
class FrameTask:
    ordinal: int
    frame_id: str
    full_rgb_path: Path
    full_semantic_path: Path
    reference_semantic_path: Path


@dataclass(frozen=True)
class FrameFeatures:
    ordinal: int
    frame_id: str
    image_width: int
    image_height: int
    whole_raw_counts: np.ndarray
    whole_counts: np.ndarray
    reference_raw_counts: np.ndarray
    reference_counts: np.ndarray
    full_kept_component_counts: np.ndarray
    full_removed_component_counts: np.ndarray
    full_removed_pixel_counts: np.ndarray
    reference_kept_component_counts: np.ndarray
    reference_removed_component_counts: np.ndarray
    reference_removed_pixel_counts: np.ndarray
    visibility_ratios: np.ndarray
    ratio_statuses: np.ndarray
    full_axis_boxes: np.ndarray
    reference_axis_boxes: np.ndarray
    full_geometry_valid: np.ndarray
    reference_geometry_valid: np.ndarray
    reference_fill_ratios: np.ndarray
    reference_aspect_ratios: np.ndarray
    reference_angles: np.ndarray
    reference_pose_statuses: np.ndarray
    source_box_exists: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "whole_counts",
            "whole_raw_counts",
            "reference_counts",
            "reference_raw_counts",
            "full_kept_component_counts",
            "full_removed_component_counts",
            "full_removed_pixel_counts",
            "reference_kept_component_counts",
            "reference_removed_component_counts",
            "reference_removed_pixel_counts",
            "visibility_ratios",
            "ratio_statuses",
            "full_geometry_valid",
            "reference_geometry_valid",
            "reference_fill_ratios",
            "reference_aspect_ratios",
            "reference_angles",
            "reference_pose_statuses",
            "source_box_exists",
        ):
            if getattr(self, name).shape != (5,):
                raise ValueError(f"{name} must have shape (5,)")
        for name in ("full_axis_boxes", "reference_axis_boxes"):
            if getattr(self, name).shape != (5, 4):
                raise ValueError(f"{name} must have shape (5, 4)")


@dataclass(frozen=True)
class FeatureMatrix:
    frame_ids: Tuple[str, ...]
    image_widths: np.ndarray
    image_heights: np.ndarray
    whole_raw_counts: np.ndarray
    whole_counts: np.ndarray
    reference_raw_counts: np.ndarray
    reference_counts: np.ndarray
    full_kept_component_counts: np.ndarray
    full_removed_component_counts: np.ndarray
    full_removed_pixel_counts: np.ndarray
    reference_kept_component_counts: np.ndarray
    reference_removed_component_counts: np.ndarray
    reference_removed_pixel_counts: np.ndarray
    visibility_ratios: np.ndarray
    ratio_statuses: np.ndarray
    full_axis_boxes: np.ndarray
    reference_axis_boxes: np.ndarray
    full_geometry_valid: np.ndarray
    reference_geometry_valid: np.ndarray
    reference_fill_ratios: np.ndarray
    reference_aspect_ratios: np.ndarray
    reference_angles: np.ndarray
    reference_pose_statuses: np.ndarray
    source_box_exists: np.ndarray

    def __post_init__(self) -> None:
        frames = len(self.frame_ids)
        if len(set(self.frame_ids)) != frames:
            raise ValueError("feature matrix contains duplicate frame IDs")
        for name in ("image_widths", "image_heights"):
            if getattr(self, name).shape != (frames,):
                raise ValueError(f"{name} must have shape ({frames},)")
        for name in (
            "whole_counts",
            "whole_raw_counts",
            "reference_counts",
            "reference_raw_counts",
            "full_kept_component_counts",
            "full_removed_component_counts",
            "full_removed_pixel_counts",
            "reference_kept_component_counts",
            "reference_removed_component_counts",
            "reference_removed_pixel_counts",
            "visibility_ratios",
            "ratio_statuses",
            "full_geometry_valid",
            "reference_geometry_valid",
            "reference_fill_ratios",
            "reference_aspect_ratios",
            "reference_angles",
            "reference_pose_statuses",
            "source_box_exists",
        ):
            if getattr(self, name).shape != (frames, 5):
                raise ValueError(f"{name} must have shape ({frames}, 5)")
        for name in ("full_axis_boxes", "reference_axis_boxes"):
            if getattr(self, name).shape != (frames, 5, 4):
                raise ValueError(f"{name} must have shape ({frames}, 5, 4)")

    @classmethod
    def from_frames(cls, frames: Tuple[FrameFeatures, ...]) -> "FeatureMatrix":
        if not frames:
            raise ValueError("cannot build feature matrix without frames")
        ordered = tuple(sorted(frames, key=lambda item: item.ordinal))
        expected = tuple(range(len(ordered)))
        actual = tuple(item.ordinal for item in ordered)
        if actual != expected:
            raise ValueError(
                f"frame feature ordinals are incomplete; expected={expected}, actual={actual}"
            )

        def stack(name: str) -> np.ndarray:
            return np.stack([getattr(item, name) for item in ordered], axis=0)

        return cls(
            frame_ids=tuple(item.frame_id for item in ordered),
            image_widths=np.asarray(
                [item.image_width for item in ordered], dtype=np.int32
            ),
            image_heights=np.asarray(
                [item.image_height for item in ordered], dtype=np.int32
            ),
            whole_raw_counts=stack("whole_raw_counts"),
            whole_counts=stack("whole_counts"),
            reference_raw_counts=stack("reference_raw_counts"),
            reference_counts=stack("reference_counts"),
            full_kept_component_counts=stack("full_kept_component_counts"),
            full_removed_component_counts=stack("full_removed_component_counts"),
            full_removed_pixel_counts=stack("full_removed_pixel_counts"),
            reference_kept_component_counts=stack(
                "reference_kept_component_counts"
            ),
            reference_removed_component_counts=stack(
                "reference_removed_component_counts"
            ),
            reference_removed_pixel_counts=stack("reference_removed_pixel_counts"),
            visibility_ratios=stack("visibility_ratios"),
            ratio_statuses=stack("ratio_statuses"),
            full_axis_boxes=stack("full_axis_boxes"),
            reference_axis_boxes=stack("reference_axis_boxes"),
            full_geometry_valid=stack("full_geometry_valid"),
            reference_geometry_valid=stack("reference_geometry_valid"),
            reference_fill_ratios=stack("reference_fill_ratios"),
            reference_aspect_ratios=stack("reference_aspect_ratios"),
            reference_angles=stack("reference_angles"),
            reference_pose_statuses=stack("reference_pose_statuses"),
            source_box_exists=stack("source_box_exists"),
        )


@dataclass(frozen=True)
class RuleMasks:
    height_width_ratios: np.ndarray
    single_visibility_bad: np.ndarray
    single_fill_bad: np.ndarray
    single_height_width_bad: np.ndarray
    single_tooth_bad: np.ndarray
    single_bad_tooth_count: np.ndarray
    drop_all_single_boxes: np.ndarray
    single_drop: np.ndarray
    single_keep: np.ndarray
    collision_visibility_bad: np.ndarray
    pose_bad: np.ndarray
    occlusion_bad_count: np.ndarray
    pose_bad_count: np.ndarray
    collision_tooth_bad: np.ndarray
    collision_bad_tooth_count: np.ndarray
    collision_drop: np.ndarray
    collision_keep: np.ndarray


@dataclass(frozen=True)
class CollisionBoxResult:
    frame_id: str
    box: PixelBox | None
    mixed_geometry_valid: bool
    action: str
    reason: str
    full_union: PixelBox | None
    reference_union: PixelBox | None


@dataclass(frozen=True)
class InputContract:
    tasks: Tuple[FrameTask, ...]
    target_ids: Tuple[int, ...]
    expected_dtype: str
    shape: Tuple[int, int]
    mapping_sha256: str


@dataclass(frozen=True)
class RunResult:
    summary: Mapping[str, object]
    output_root: Path
