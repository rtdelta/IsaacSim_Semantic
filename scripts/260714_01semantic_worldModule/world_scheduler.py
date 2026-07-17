"""Fixed-step world and timeline scheduling."""

from __future__ import annotations

from typing import Any

import carb.settings
import omni.timeline


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
        self._started = False

    def initialize(self) -> None:
        settings = carb.settings.get_settings()
        settings.set("/app/player/useFixedTimeStepping", True)
        self._timeline.set_looping(False)
        self._timeline.set_current_time(0.0)
        self._timeline.set_time_codes_per_second(float(self.physics_hz))
        self._timeline.set_end_time(max(self.maximum_duration_seconds, 1.0))
        self._timeline.commit()
        print(
            f"[world-scheduler] Fixed step configured: {self.physics_hz} Hz "
            f"(dt={self.physics_dt:.9f}s)"
        )

    @property
    def simulation_time(self) -> float:
        return self._step_count * self.physics_dt

    @property
    def next_simulation_time(self) -> float:
        return (self._step_count + 1) * self.physics_dt

    def start(self) -> None:
        if self._started:
            return
        self._timeline.play()
        self._timeline.commit()
        self._started = True
        print("[world-scheduler] Timeline playing")

    def update(self, simulation_time: float) -> None:
        """Update scheduled world attributes before the next physics step.

        Version 1 intentionally keeps lights, materials, and environment static.
        The method is the isolated extension point for future world scheduling.
        """
        _ = simulation_time

    def step(self) -> float:
        if not self._started:
            raise RuntimeError("WorldScheduler.start() must be called before step()")
        self._app.update()
        self._step_count += 1
        return self.simulation_time

    def stop(self) -> None:
        if self._timeline.is_playing():
            self._timeline.pause()
            self._timeline.commit()
        self._started = False

    def get_state(self) -> dict[str, Any]:
        return {
            "physics_hz": self.physics_hz,
            "physics_dt": self.physics_dt,
            "physics_step": self._step_count,
            "simulation_time": self.simulation_time,
            "timeline_time": float(self._timeline.get_current_time()),
        }
