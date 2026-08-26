from __future__ import annotations

import unittest
from types import SimpleNamespace

from semantic_world_v03.models import AcquisitionKind, SensorCapabilities
from semantic_world_v03.rendering import RenderGroupManager


class Backend:
    def __init__(self):
        self.renders = []

    def render(self, *, rt_subframes):
        self.renders.append(rt_subframes)


class Driver:
    capabilities = SensorCapabilities(AcquisitionKind.SNAPSHOT, ("rgb",), True)

    def __init__(self, name):
        self.name = name
        self.samples = 0

    def read(self, request):
        return self.name

    def mark_sample_captured(self):
        self.samples += 1


class RenderGroupTests(unittest.TestCase):
    def test_group_triggers_one_render_for_multiple_cameras(self):
        backend = Backend()
        manager = RenderGroupManager(backend, {"group": SimpleNamespace(rt_subframes=8)})
        first, second = Driver("first"), Driver("second")
        request = SimpleNamespace(render_group="group")
        self.assertEqual(
            manager.acquire([(first, request), (second, request)]), ("first", "second")
        )
        self.assertEqual(backend.renders, [8])
        self.assertEqual(first.samples, 1)
        self.assertEqual(second.samples, 1)


if __name__ == "__main__":
    unittest.main()

