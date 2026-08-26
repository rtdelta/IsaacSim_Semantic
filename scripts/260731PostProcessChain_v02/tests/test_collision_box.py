from __future__ import annotations

import unittest

import numpy as np

from postprocess_chain_v02.modules.collision_box.config import CollisionBoxConfig
from postprocess_chain_v02.modules.collision_box.module import build_collision_box


class CollisionBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.full = np.asarray(
            [[1, 20, 10, 30], [20, 22, 50, 40]] + [[-1, -1, -1, -1]] * 3
        )
        self.reference = np.asarray(
            [[5, 10, 15, 25], [25, 15, 55, 60]] + [[-1, -1, -1, -1]] * 3
        )
        self.valid = np.asarray([True, True, False, False, False])

    def _config(self, axis: str) -> CollisionBoxConfig:
        return CollisionBoxConfig(
            True, axis, "full_scene", "reference", "all_valid_teeth"
        )

    def test_x_axis_uses_full_x_and_reference_y(self) -> None:
        result = build_collision_box(
            "0000",
            self.full,
            self.reference,
            self.valid,
            self.valid,
            True,
            100,
            100,
            self._config("x"),
        )
        self.assertEqual(result.box.as_tuple(), (1, 10, 50, 60))

    def test_y_axis_uses_full_y_and_reference_x(self) -> None:
        result = build_collision_box(
            "0000",
            self.full,
            self.reference,
            self.valid,
            self.valid,
            True,
            100,
            100,
            self._config("y"),
        )
        self.assertEqual(result.box.as_tuple(), (5, 20, 55, 40))


if __name__ == "__main__":
    unittest.main()
