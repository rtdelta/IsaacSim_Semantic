from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple


@dataclass(frozen=True)
class ClassesConfig:
    tooth_class_name: str
    collision_class_name: str


@dataclass(frozen=True)
class OutputConfig:
    preserve_reports: bool
    unchanged_file_mode: str


@dataclass(frozen=True)
class PerformanceConfig:
    workers: int
    max_in_flight: int


@dataclass(frozen=True)
class RunConfig:
    schema_version: int
    config_path: Path
    input_root: Path
    output_root: Path
    filename_prefix: str
    classes: ClassesConfig
    output: OutputConfig
    performance: PerformanceConfig


@dataclass(frozen=True)
class FrameFiles:
    numeric_frame_id: int
    rgb_frame_token: str
    tooth_frame_token: str
    collision_frame_token: str
    rgb_path: Path
    tooth_label_path: Path
    collision_label_path: Path


@dataclass(frozen=True)
class DatasetContract:
    frames: Tuple[FrameFiles, ...]
    max_frame_id: int
    padding_width: int


@dataclass(frozen=True)
class FramePlan:
    source: FrameFiles
    normalized_frame_id: str
    rgb_name: str
    tooth_label_name: str
    collision_label_name: str


@dataclass(frozen=True)
class LabelTransformResult:
    category: str
    source: Path
    destination: Path
    line_count: int
    empty: bool
    original_classes: Mapping[int, int]


@dataclass(frozen=True)
class MaterializeOperation:
    category: str
    source: Path
    destination: Path


@dataclass(frozen=True)
class MaterializeResult:
    category: str
    source: Path
    destination: Path
    mode: str
    size: int
