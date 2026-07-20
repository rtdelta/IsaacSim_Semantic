"""Pure timing math for fixed-step semantic-camera capture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureTiming:
    physics_hz: int
    capture_fps: int
    capture_initial_frame: bool = True
    static: bool = False

    def __post_init__(self) -> None:
        if self.physics_hz <= 0 or self.capture_fps <= 0:
            raise ValueError("physics_hz and capture_fps must be positive")
        if self.physics_hz % self.capture_fps != 0:
            raise ValueError("physics_hz must be divisible by capture_fps")

    @property
    def steps_per_capture(self) -> int:
        return self.physics_hz // self.capture_fps

    def data_step_for_frame(self, frame_id: int) -> int:
        if frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        if self.static:
            return 0
        offset = 0 if self.capture_initial_frame else 1
        return (frame_id + offset) * self.steps_per_capture

    def dataset_time_for_frame(self, frame_id: int) -> float:
        return self.data_step_for_frame(frame_id) / float(self.physics_hz)
