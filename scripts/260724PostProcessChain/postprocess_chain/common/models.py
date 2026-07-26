from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple


@dataclass(frozen=True)
class FrameTask:
    frame_id: str
    rgb_path: Path
    semantic_path: Path


@dataclass(frozen=True)
class PixelBox:
    """Pixel-aligned half-open box: [left, top, right, bottom)."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0:
            raise ValueError("box left/top must be non-negative")
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("box right/bottom must be greater than left/top")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0


@dataclass(frozen=True)
class SemanticBox:
    semantic_label: str
    semantic_id: int
    pixel_count: int
    box: PixelBox


@dataclass(frozen=True)
class SemanticBoxSet:
    boxes: Tuple[SemanticBox, ...]

    def by_label(self) -> Dict[str, SemanticBox]:
        return {item.semantic_label: item for item in self.boxes}


@dataclass(frozen=True)
class YoloDetection:
    class_id: int
    class_name: str
    box: PixelBox


@dataclass(frozen=True)
class YoloAnnotationSet:
    detections: Tuple[YoloDetection, ...]


@dataclass(frozen=True)
class ModuleOutputConfig:
    directory: Path
    layout: str


@dataclass
class ModuleResult:
    artifacts: Mapping[str, object] = field(default_factory=dict)
    annotation: Optional[YoloAnnotationSet] = None
    disposition: str = "write"
    metrics: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.disposition not in {"write", "exclude"}:
            raise ValueError(f"unsupported module disposition: {self.disposition}")


@dataclass(frozen=True)
class SemanticMapping:
    label_to_id: Mapping[str, int]
    expected_dtype: str
