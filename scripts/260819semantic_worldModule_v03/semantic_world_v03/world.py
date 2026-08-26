"""Fixed-step Isaac world controller and immutable capture snapshots."""

from __future__ import annotations

from enum import Enum
from typing import Any

from .config import SceneConfig
from .models import WorldSnapshot, jsonable


class WorldState(str, Enum):
    NEW = "new"
    RUNNING = "running"
    FROZEN = "frozen"
    STOPPED = "stopped"


class WorldController:
    def __init__(self, simulation_app: Any, stage: Any, scene: SceneConfig) -> None:
        import omni.timeline

        self.app = simulation_app
        self.stage = stage
        self.scene = scene
        self.physics_hz = scene.physics_hz
        self.physics_step = 0
        self.timeline = omni.timeline.get_timeline_interface()
        self.state = WorldState.NEW

    def initialize(self, maximum_dataset_steps: int) -> None:
        import carb.settings

        settings = carb.settings.get_settings()
        settings.set("/app/player/useFixedTimeStepping", True)
        self.timeline.set_looping(False)
        self.timeline.set_current_time(0.0)
        self.timeline.set_time_codes_per_second(float(self.physics_hz))
        self.timeline.set_end_time(max(1.0, maximum_dataset_steps / self.physics_hz + 1.0))
        self.timeline.commit()
        self.timeline.play()
        self.timeline.commit()
        self.state = WorldState.RUNNING
        for _ in range(self.scene.pre_roll_steps):
            self.app.update()
        self.physics_step = 0

    def advance_to(
        self,
        target_step: int,
        progress_callback: Any = None,
        before_step_callback: Any = None,
        after_step_callback: Any = None,
    ) -> None:
        if self.state is WorldState.FROZEN:
            self.resume()
        if self.state is not WorldState.RUNNING:
            raise RuntimeError(f"Cannot advance world from {self.state.value}")
        if target_step < self.physics_step:
            raise RuntimeError(
                f"Cannot rewind worker world from step {self.physics_step} to {target_step}"
            )
        while self.physics_step < target_step:
            next_time = (self.physics_step + 1) / self.physics_hz
            if before_step_callback is not None:
                before_step_callback(next_time)
            self.app.update()
            self.physics_step += 1
            if after_step_callback is not None:
                after_step_callback(self.physics_step / self.physics_hz)
            if progress_callback is not None:
                progress_callback(self.physics_step)

    def seek_to_absolute_step(
        self,
        target_step: int,
        apply_state_callback: Any,
    ) -> None:
        """Jump to an absolute dataset step without replaying prior physics.

        This is intentionally opt-in: callers must supply a callback that can
        reconstruct the complete driven state at ``target_step``.  It is safe
        for the CSV articulation driver, whose samples contain absolute joint
        positions and an absolute root pose, but not for a motion driver whose
        state depends on integrating earlier steps.

        For a positive target, the timeline is positioned one fixed step
        earlier and advanced exactly once after applying the target's absolute
        pose.  This reproduces the final physics/render synchronization tick
        performed by normal sequential playback.  Step zero has no preceding
        tick, so it uses one paused propagation update instead.  The timeline
        remains frozen on return.
        """

        if target_step < 0:
            raise ValueError("target_step must be non-negative")
        if not callable(apply_state_callback):
            raise TypeError("apply_state_callback must be callable")
        if self.state is WorldState.RUNNING:
            self.timeline.pause()
            self.timeline.commit()
            self.state = WorldState.FROZEN
        if self.state is not WorldState.FROZEN:
            raise RuntimeError(f"Cannot seek world from {self.state.value}")

        target_time = target_step / self.physics_hz
        if target_step == 0:
            self.timeline.set_current_time(0.0)
            self.timeline.commit()
            apply_state_callback(0.0)
            self.app.update()
        else:
            self.timeline.set_current_time((target_step - 1) / self.physics_hz)
            self.timeline.commit()
            # The normal advance loop applies the absolute pose for the next
            # time before stepping physics.  Preserve that ordering here.
            apply_state_callback(target_time)
            self.timeline.play()
            self.timeline.commit()
            self.app.update()
            self.timeline.pause()
            self.timeline.commit()
        self.physics_step = target_step

    def freeze(self) -> WorldSnapshot:
        if self.state is WorldState.RUNNING:
            self.timeline.pause()
            self.timeline.commit()
            self.state = WorldState.FROZEN
        if self.state is not WorldState.FROZEN:
            raise RuntimeError(f"Cannot freeze world from {self.state.value}")
        values: dict[str, Any] = {}
        if self.scene.state_prim_paths:
            from pxr import Usd, UsdGeom

            timeline_time = float(self.timeline.get_current_time())
            cache = UsdGeom.XformCache(
                Usd.TimeCode(timeline_time * float(self.stage.GetTimeCodesPerSecond()))
            )
            for path in self.scene.state_prim_paths:
                prim = self.stage.GetPrimAtPath(path)
                if prim is None or not prim.IsValid():
                    raise RuntimeError(f"State prim does not exist: {path}")
                matrix = cache.GetLocalToWorldTransform(prim)
                values[path] = [
                    float(matrix[row][column]) for row in range(4) for column in range(4)
                ]
        return WorldSnapshot(
            physics_step=self.physics_step,
            dataset_time=self.physics_step / self.physics_hz,
            timeline_time=float(self.timeline.get_current_time()),
            state=jsonable(values),
        )

    def assert_frozen(self, snapshot: WorldSnapshot) -> None:
        if self.state is not WorldState.FROZEN or self.physics_step != snapshot.physics_step:
            raise RuntimeError("Physics advanced during sensor acquisition")

    def resume(self) -> None:
        if self.state is WorldState.FROZEN:
            self.timeline.play()
            self.timeline.commit()
            self.state = WorldState.RUNNING

    def close(self) -> None:
        if self.state is not WorldState.STOPPED:
            self.timeline.pause()
            self.timeline.commit()
            self.state = WorldState.STOPPED


def open_stage_and_wait(simulation_app: Any, stage_path: str, max_updates: int = 1200) -> Any:
    import omni.usd

    context = omni.usd.get_context()
    if not context.open_stage(stage_path):
        raise RuntimeError(f"Could not start opening USD stage: {stage_path}")
    last_status: Any = None
    for _ in range(max_updates):
        simulation_app.update()
        stage = context.get_stage()
        last_status = context.get_stage_loading_status()
        pending = int(last_status[2]) if len(last_status) > 2 else 0
        if stage is not None and pending == 0 and stage.GetPseudoRoot().GetChildren():
            return stage
    raise TimeoutError(f"USD stage did not finish loading: status={last_status}")
