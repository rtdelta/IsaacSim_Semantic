"""Pure-Python ordering tests for fixed-step scheduler callbacks."""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import patch


class FakeSettings:
    def __init__(self) -> None:
        self.values = {}

    def set(self, key, value) -> None:
        self.values[key] = value


class FakeTimeline:
    def __init__(self) -> None:
        self.current_time = 0.0
        self.playing = False

    def set_looping(self, value):
        self.looping = value

    def set_current_time(self, value):
        self.current_time = float(value)

    def set_time_codes_per_second(self, value):
        self.time_codes_per_second = value

    def set_end_time(self, value):
        self.end_time = value

    def commit(self):
        pass

    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False

    def is_playing(self):
        return self.playing

    def get_current_time(self):
        return self.current_time


class FakeApp:
    def __init__(self, timeline: FakeTimeline, events: list) -> None:
        self.timeline = timeline
        self.events = events
        self.updates = 0

    def update(self):
        self.events.append(("step", None))
        self.updates += 1
        self.timeline.current_time += 1.0 / 60.0


def load_scheduler_module(timeline: FakeTimeline, settings: FakeSettings):
    carb_package = types.ModuleType("carb")
    carb_settings = types.ModuleType("carb.settings")
    carb_settings.get_settings = lambda: settings
    carb_package.settings = carb_settings
    omni_package = types.ModuleType("omni")
    omni_timeline = types.ModuleType("omni.timeline")
    omni_timeline.get_timeline_interface = lambda: timeline
    omni_package.timeline = omni_timeline
    modules = {
        "carb": carb_package,
        "carb.settings": carb_settings,
        "omni": omni_package,
        "omni.timeline": omni_timeline,
    }
    sys.modules.pop("world_scheduler", None)
    with patch.dict(sys.modules, modules):
        return importlib.import_module("world_scheduler")


class WorldSchedulerHookTests(unittest.TestCase):
    def make_scheduler(self):
        events = []
        timeline = FakeTimeline()
        module = load_scheduler_module(timeline, FakeSettings())
        app = FakeApp(timeline, events)
        scheduler = module.WorldScheduler(app, object(), 60, 5.0)
        scheduler.initialize()
        scheduler.start()
        return scheduler, app, events

    def test_before_and_after_hooks_bracket_each_counted_step(self) -> None:
        scheduler, _app, events = self.make_scheduler()

        scheduler.advance_exact_steps(
            2,
            before_step_callback=lambda value: events.append(("before", value)),
            after_step_callback=lambda value: events.append(("after", value)),
        )

        self.assertEqual([event[0] for event in events], [
            "before", "step", "after", "before", "step", "after"
        ])
        self.assertAlmostEqual(events[0][1], 1.0 / 60.0)
        self.assertAlmostEqual(events[2][1], 1.0 / 60.0)
        self.assertAlmostEqual(events[3][1], 2.0 / 60.0)
        self.assertAlmostEqual(events[5][1], 2.0 / 60.0)
        self.assertEqual(scheduler.get_state()["physics_step"], 2)

    def test_bootstrap_steps_are_counted_and_bounded(self) -> None:
        scheduler, app, _events = self.make_scheduler()

        completed = scheduler.bootstrap_until(lambda: app.updates >= 2, max_steps=4)

        self.assertEqual(completed, 2)
        self.assertEqual(scheduler.get_state()["physics_step"], 2)

    def test_bootstrap_timeout_is_explicit(self) -> None:
        scheduler, _app, _events = self.make_scheduler()
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            scheduler.bootstrap_until(lambda: False, max_steps=2)
        self.assertEqual(scheduler.get_state()["physics_step"], 2)


if __name__ == "__main__":
    unittest.main()
