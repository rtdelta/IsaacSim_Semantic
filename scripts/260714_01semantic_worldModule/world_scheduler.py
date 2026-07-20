"""Fixed-step world and timeline scheduling."""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import Any

import carb.settings
import omni.timeline

from capture_context import FrozenWorldSnapshot


class WorldState(Enum):
    NEW = auto()
    INITIALIZED = auto()
    RUNNING = auto()
    FROZEN = auto()
    STOPPED = auto()


class WorldScheduler:
    """Own timeline control, physics stepping, and future world-attribute updates."""

    def __init__(
        self,
        simulation_app: Any,
        stage: Any,
        physics_hz: int,
        maximum_duration_seconds: float,
    ) -> None:
        self._app = simulation_app
        self._stage = stage
        self.physics_hz = int(physics_hz)
        self.physics_dt = 1.0 / float(self.physics_hz)
        self.maximum_duration_seconds = float(maximum_duration_seconds)
        self._timeline = omni.timeline.get_timeline_interface()
        self._step_count = 0
        self._dataset_origin_step = 0
        self._state = WorldState.NEW

    def initialize(self) -> None:
        if self._state is not WorldState.NEW:
            raise RuntimeError(f"WorldScheduler cannot initialize from state {self._state.name}")
        settings = carb.settings.get_settings()
        settings.set("/app/player/useFixedTimeStepping", True)
        self._timeline.set_looping(False)
        self._timeline.set_current_time(0.0)
        self._timeline.set_time_codes_per_second(float(self.physics_hz))
        self._timeline.set_end_time(max(self.maximum_duration_seconds, 1.0))
        self._timeline.commit()
        self._state = WorldState.INITIALIZED
        print(
            f"[world-scheduler] Fixed step configured: {self.physics_hz} Hz "
            f"(dt={self.physics_dt:.9f}s)"
        )

    @property
    def simulation_time(self) -> float:
        """Total physics time, including any pre-roll steps."""
        return self._step_count * self.physics_dt

    @property
    def next_simulation_time(self) -> float:
        return (self._step_count + 1) * self.physics_dt

    @property
    def dataset_step(self) -> int:
        return self._step_count - self._dataset_origin_step

    @property
    def dataset_time(self) -> float:
        return self.dataset_step * self.physics_dt

    @property
    def next_dataset_time(self) -> float:
        return (self.dataset_step + 1) * self.physics_dt

    @property
    def state(self) -> WorldState:
        return self._state

    def start(self) -> None:
        if self._state is WorldState.RUNNING:
            return
        if self._state is not WorldState.INITIALIZED:
            raise RuntimeError(f"WorldScheduler cannot start from state {self._state.name}")
        self._timeline.play()
        self._timeline.commit()
        self._state = WorldState.RUNNING
        print("[world-scheduler] Timeline playing")

    def begin_data_timeline(self) -> None:
        if self._state not in {WorldState.RUNNING, WorldState.FROZEN}:
            raise RuntimeError(
                f"Cannot establish dataset time origin from state {self._state.name}"
            )
        self._dataset_origin_step = self._step_count
        print(
            f"[world-scheduler] Dataset time origin set at physics step {self._step_count} "
            f"(timeline={float(self._timeline.get_current_time()):.9f}s)"
        )

    def update(self, simulation_time: float) -> None:
        """Update scheduled world attributes before the next physics step.

        Version 1 intentionally keeps lights, materials, and environment static.
        The method is the isolated extension point for future world scheduling.
        """
        _ = simulation_time

    def step(self) -> float:
        if self._state is not WorldState.RUNNING:
            raise RuntimeError(f"WorldScheduler cannot step from state {self._state.name}")
        self._app.update()
        self._step_count += 1
        return self.simulation_time

    def advance_exact_steps(self, count: int, before_step_callback: Any = None) -> float:
        if count < 0:
            raise ValueError("Step count must be non-negative")
        if self._state is not WorldState.RUNNING:
            raise RuntimeError(f"WorldScheduler cannot advance from state {self._state.name}")
        for _ in range(count):
            next_time = self.next_dataset_time
            self.update(next_time)
            if before_step_callback is not None:
                before_step_callback(next_time)
            self.step()
        return self.dataset_time

    def freeze_for_capture(self) -> FrozenWorldSnapshot:
        if self._state is WorldState.FROZEN:
            return FrozenWorldSnapshot(
                physics_step=self._step_count,
                dataset_time=self.dataset_time,
                timeline_time=float(self._timeline.get_current_time()),
            )
        if self._state is not WorldState.RUNNING:
            raise RuntimeError(f"WorldScheduler cannot freeze from state {self._state.name}")
        self._timeline.pause()
        self._timeline.commit()
        self._state = WorldState.FROZEN
        return FrozenWorldSnapshot(
            physics_step=self._step_count,
            dataset_time=self.dataset_time,
            timeline_time=float(self._timeline.get_current_time()),
        )

    def assert_still_frozen(
        self,
        snapshot: FrozenWorldSnapshot,
        absolute_tolerance: float = 1e-9,
    ) -> None:
        if self._state is not WorldState.FROZEN:
            raise RuntimeError(f"World is no longer frozen; current state is {self._state.name}")
        if self._step_count != snapshot.physics_step:
            raise RuntimeError(
                f"Physics advanced during capture: {snapshot.physics_step} -> {self._step_count}"
            )
        timeline_time = float(self._timeline.get_current_time())
        if not math.isclose(
            timeline_time,
            snapshot.timeline_time,
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ):
            raise RuntimeError(
                "Timeline advanced during capture: "
                f"{snapshot.timeline_time:.12f} -> {timeline_time:.12f}"
            )

    def resume_after_capture(self) -> None:
        if self._state is not WorldState.FROZEN:
            raise RuntimeError(f"WorldScheduler cannot resume from state {self._state.name}")
        self._timeline.play()
        self._timeline.commit()
        self._state = WorldState.RUNNING

    def stop(self) -> None:
        if self._timeline.is_playing():
            self._timeline.pause()
            self._timeline.commit()
        self._state = WorldState.STOPPED

    def get_state(self) -> dict[str, Any]:
        return {
            "physics_hz": self.physics_hz,
            "physics_dt": self.physics_dt,
            "physics_step": self._step_count,
            "simulation_time": self.simulation_time,
            "dataset_origin_step": self._dataset_origin_step,
            "dataset_step": self.dataset_step,
            "dataset_time": self.dataset_time,
            "timeline_time": float(self._timeline.get_current_time()),
            "state": self._state.name.lower(),
        }
