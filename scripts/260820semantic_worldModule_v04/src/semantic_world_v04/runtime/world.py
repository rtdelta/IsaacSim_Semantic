"""Deterministic physics stepping and absolute-seek boundaries."""

from typing import Any


class TimelineWorld:
    def __init__(self, simulation_app: Any, physics_hz: int) -> None:
        import omni.timeline  # type: ignore

        self.app = simulation_app
        self.physics_hz = physics_hz
        self.timeline = omni.timeline.get_timeline_interface()
        self.physics_step = 0
        self.simulation_context = None

    def initialize(self, motion: Any) -> None:
        self.timeline.pause()
        self.timeline.set_current_time(0.0)
        self.timeline.commit()
        if bool(getattr(motion, "requires_physics", False)):
            self._initialize_physics()
        motion.initialize()
        if bool(getattr(motion, "supports_absolute_seek", False)):
            motion.seek(0.0)
        else:
            motion.apply(0.0)
        self.app.update()
        self.physics_step = 0

    def seek_to_absolute_step(self, target_step: int, motion: Any) -> None:
        if target_step < 0:
            raise ValueError("target_step must not be negative")
        if not bool(getattr(motion, "supports_absolute_seek", False)):
            raise ValueError("motion source does not support absolute seek")
        self.timeline.pause()
        if target_step == 0:
            self.timeline.set_current_time(0.0)
            self.timeline.commit()
            motion.seek(0.0)
            self.app.update()
            self.physics_step = 0
            return
        target_time = target_step / float(self.physics_hz)
        previous_time = (target_step - 1) / float(self.physics_hz)
        self.timeline.set_current_time(previous_time)
        self.timeline.commit()
        motion.seek(target_time)
        self.timeline.play()
        self.timeline.commit()
        self.app.update()
        self.timeline.pause()
        self.timeline.commit()
        self.physics_step = target_step

    def advance_to(self, target_step: int, motion: Any) -> None:
        if target_step < self.physics_step:
            self.seek_to_absolute_step(target_step, motion)
            return
        self.timeline.play()
        self.timeline.commit()
        while self.physics_step < target_step:
            next_step = self.physics_step + 1
            motion.apply(next_step / float(self.physics_hz))
            self.app.update()
            self.physics_step = next_step
        self.timeline.pause()
        self.timeline.commit()

    def restore_after_capture(self) -> None:
        """Restore logical time after Replicator's internal scheduling updates."""

        self.timeline.pause()
        self.timeline.set_current_time(
            self.physics_step / float(self.physics_hz)
        )
        self.timeline.commit()

    def close(self) -> None:
        self.timeline.pause()
        self.timeline.commit()
        if self.simulation_context is not None:
            context_type = type(self.simulation_context)
            try:
                self.simulation_context.stop()
            finally:
                context_type.clear_instance()
                self.simulation_context = None

    def _initialize_physics(self) -> None:
        """Create the tensor simulation view required by articulations."""

        from isaacsim.core.api import SimulationContext  # type: ignore

        context = SimulationContext.instance()
        if context is None:
            context = SimulationContext(
                physics_dt=1.0 / float(self.physics_hz),
                rendering_dt=1.0 / float(self.physics_hz),
                backend="numpy",
            )
        context.reset()
        self.app.update()
        self.timeline.pause()
        self.timeline.set_current_time(0.0)
        self.timeline.commit()
        self.simulation_context = context
