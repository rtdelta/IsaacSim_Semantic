from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple


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

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    def validate_inside(self, image_width: int, image_height: int) -> None:
        if image_width <= 0 or image_height <= 0:
            raise ValueError("image dimensions must be positive")
        if self.right > image_width or self.bottom > image_height:
            raise ValueError(
                f"box {self} exceeds image size ({image_width}, {image_height})"
            )

    @classmethod
    def from_values(cls, values: Sequence[int]) -> "PixelBox":
        if len(values) != 4:
            raise ValueError("pixel box requires four values")
        return cls(*(int(value) for value in values))


def union_boxes(boxes: Iterable[Optional[PixelBox]]) -> Optional[PixelBox]:
    selected = [box for box in boxes if box is not None]
    if not selected:
        return None
    return PixelBox(
        left=min(box.left for box in selected),
        top=min(box.top for box in selected),
        right=max(box.right for box in selected),
        bottom=max(box.bottom for box in selected),
    )
