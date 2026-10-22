"""Check the external geometry dependency and the distance convention we use."""
import unittest
from pathlib import Path

import numpy as np
import trimesh


class GeometryDependencyTests(unittest.TestCase):
    def test_pinned_external_package(self):
        self.assertEqual(trimesh.__version__, "4.12.2")
        vendor = Path(__file__).resolve().parent / "vendor"
        self.assertFalse(Path(trimesh.__file__).resolve().is_relative_to(vendor))

    def test_world_space_point_to_triangle_distance(self):
        mesh = trimesh.Trimesh(vertices=[[0, 0, 0], [2, 0, 0], [0, 2, 0]],
                               faces=[[0, 1, 2]], process=False)
        nearest, distances, triangles = trimesh.proximity.closest_point(
            mesh, np.array([[0.5, 0.5, 3.0], [0.5, 0.5, -2.0]]))
        np.testing.assert_allclose(distances, [3.0, 2.0], atol=1e-12)
        np.testing.assert_allclose(nearest, [[0.5, 0.5, 0.0]] * 2, atol=1e-12)
        np.testing.assert_array_equal(triangles, [0, 0])


if __name__ == "__main__":
    unittest.main()
