"""Checks interpolation/coordinate conventions and rejects epoch mixing."""
import unittest
import numpy as np
from deskew import PoseHistory


class DeskewTests(unittest.TestCase):
    def test_translating_and_rotating_sensor(self):
        # At t=0.5 s: translation (1,0,0), 45 degrees around Z.
        h = PoseHistory([0, 1_000_000_000], [[0,0,0],[2,0,0]],
                        [[0,0,0,1],[0,0,np.sqrt(.5),np.sqrt(.5)]])
        p = h.deskew([[1,0,0]], [500_000_000])
        np.testing.assert_allclose(p, [[1+np.sqrt(.5),np.sqrt(.5),0]], atol=1e-12)
        np.testing.assert_allclose(h.deskew([[1,0,0]], [500_000_000], 500_000_000),
                                   [[1,0,0]], atol=1e-12)

    def test_quaternion_sign_does_not_change_pose(self):
        h = PoseHistory([0,10], [[0,0,0],[0,0,0]], [[0,0,0,1],[0,0,0,-1]])
        np.testing.assert_allclose(h.deskew([[1,2,3]], [5]), [[1,2,3]])

    def test_no_silent_extrapolation_or_epoch_mixing(self):
        with self.assertRaises(ValueError):
            PoseHistory([0,10,0], np.zeros((3,3)), [[0,0,0,1]]*3)
        h = PoseHistory([0,10], [[0,0,0],[0,0,0]], [[0,0,0,1]]*2)
        with self.assertRaises(ValueError):
            h.deskew([[1,0,0]], [11])


if __name__ == '__main__':
    unittest.main()
