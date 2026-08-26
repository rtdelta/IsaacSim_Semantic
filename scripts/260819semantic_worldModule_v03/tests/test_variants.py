from __future__ import annotations

import unittest

from semantic_world_v03.variants import select_isolation_paths


class VariantIsolationTests(unittest.TestCase):
    def test_selects_minimal_roots_outside_whitelist_and_sensor_branches(self):
        imageable = [
            "/World",
            "/World/Site",
            "/World/Site/Excavator",
            "/World/Site/Excavator/Body",
            "/World/Site/Buildings",
            "/World/Site/Ground",
            "/World/Sensors",
            "/World/Sensors/FrontCamera",
            "/World/Unrelated",
            "/World/Unrelated/Child",
        ]
        selected = select_isolation_paths(
            imageable,
            ["/World/Site/Excavator", "/World/Sensors/FrontCamera"],
        )
        self.assertEqual(
            selected,
            (
                "/World/Unrelated",
                "/World/Site/Buildings",
                "/World/Site/Ground",
            ),
        )
        self.assertNotIn("/World/Sensors", selected)
        self.assertNotIn("/World/Sensors/FrontCamera", selected)

    def test_empty_whitelist_would_hide_shallowest_imageable(self):
        self.assertEqual(
            select_isolation_paths(["/World", "/World/A", "/World/B"], []),
            ("/World",),
        )


if __name__ == "__main__":
    unittest.main()
