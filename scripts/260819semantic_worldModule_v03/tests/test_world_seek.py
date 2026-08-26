from __future__ import annotations

import unittest

from semantic_world_v03.world import WorldController, WorldState


class _App:
    def __init__(self, timeline=None, physics_hz: int = 60) -> None:
        self.updates = 0
        self.timeline = timeline
        self.physics_hz = physics_hz

    def update(self) -> None:
        self.updates += 1
        if self.timeline is not None and self.timeline.playing:
            self.timeline.current_time += 1.0 / self.physics_hz


class _Timeline:
    def __init__(self) -> None:
        self.current_time = 0.0
        self.pauses = 0
        self.plays = 0
        self.commits = 0
        self.playing = False

    def pause(self) -> None:
        self.pauses += 1
        self.playing = False

    def play(self) -> None:
        self.plays += 1
        self.playing = True

    def commit(self) -> None:
        self.commits += 1

    def set_current_time(self, value: float) -> None:
        self.current_time = value


class WorldSeekTests(unittest.TestCase):
    def test_absolute_seek_sets_time_pose_and_step_without_replay(self):
        world = WorldController.__new__(WorldController)
        world.timeline = _Timeline()
        world.app = _App(world.timeline)
        world.physics_hz = 60
        world.physics_step = 0
        world.state = WorldState.RUNNING
        applied: list[float] = []

        world.seek_to_absolute_step(600, applied.append)

        self.assertEqual(world.state, WorldState.FROZEN)
        self.assertEqual(world.physics_step, 600)
        self.assertEqual(world.timeline.current_time, 10.0)
        self.assertEqual(applied, [10.0])
        self.assertEqual(world.app.updates, 1)
        self.assertEqual(world.timeline.plays, 1)
        self.assertEqual(world.timeline.pauses, 2)

    def test_absolute_seek_to_zero_does_not_advance_physics(self):
        world = WorldController.__new__(WorldController)
        world.timeline = _Timeline()
        world.app = _App(world.timeline)
        world.physics_hz = 60
        world.physics_step = 12
        world.state = WorldState.RUNNING
        applied: list[float] = []

        world.seek_to_absolute_step(0, applied.append)

        self.assertEqual(world.state, WorldState.FROZEN)
        self.assertEqual(world.physics_step, 0)
        self.assertEqual(world.timeline.current_time, 0.0)
        self.assertEqual(applied, [0.0])
        self.assertEqual(world.app.updates, 1)
        self.assertEqual(world.timeline.plays, 0)
        self.assertEqual(world.timeline.pauses, 1)

    def test_absolute_seek_rejects_negative_step(self):
        world = WorldController.__new__(WorldController)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            world.seek_to_absolute_step(-1, lambda _: None)


if __name__ == "__main__":
    unittest.main()
