import json
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np
from lidar_visualizer.reference_frames import HorizontalFrame, quaternion_matrix
from lidar_visualizer.config import load_config, validate_sensors


def rpy_quat(roll, pitch, yaw):
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    return [sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy,
            cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy]


class ReferenceFramesTest(unittest.TestCase):
    def test_initial_axes_and_shared_position(self):
        row = HorizontalFrame().update([1,2,3], [0,0,0,1])
        self.assertEqual(row['position'], [1,2,3])
        self.assertEqual(row['xyzw'], [0,0,0,1])
        self.assertTrue(row['heading_valid'])

    def test_combined_tilt_yaw_and_point_reconstruction(self):
        rng = np.random.default_rng(410)
        h = HorizontalFrame()
        for _ in range(150):
            roll, pitch, yaw = rng.uniform([-3,-1.4,-math.pi], [3,1.4,math.pi])
            p, point = rng.normal(size=(2,3))
            q = rpy_quat(roll, pitch, yaw)
            row = h.update(p, q)
            H, S = quaternion_matrix(row['xyzw']), quaternion_matrix(q)
            np.testing.assert_allclose(H[:,2], [0,0,1], atol=1e-14)
            np.testing.assert_allclose(H[:,0], [math.cos(yaw),math.sin(yaw),0], atol=1e-14)
            np.testing.assert_allclose(H @ (H.T @ S @ point) + p, S @ point + p, atol=1e-13)
            self.assertAlmostEqual(np.linalg.det(H), 1.)

    def test_yaw_wrap_preserves_quaternion_sign_continuity(self):
        h = HorizontalFrame()
        a = h.update([0,0,0], rpy_quat(.2,.3,math.pi-.001))['xyzw']
        b = h.update([0,0,0], rpy_quat(.2,.3,-math.pi+.001))['xyzw']
        self.assertGreater(np.dot(a,b), .999)

    def test_singularity_holds_heading_and_recovers(self):
        h = HorizontalFrame()
        h.update([0,0,0], rpy_quat(0,0,.6))
        row = h.update([4,5,6], rpy_quat(0,math.pi/2,1.2))
        self.assertFalse(row['heading_valid'])
        self.assertEqual(row['position'], [4,5,6])
        self.assertAlmostEqual(row['heading_rad'], .6)
        row = h.update([0,0,0], rpy_quat(0,.3,1.2))
        self.assertTrue(row['heading_valid'])
        self.assertAlmostEqual(row['heading_rad'], 1.2)
        h.reset()
        row = h.update([0,0,0], rpy_quat(0,math.pi/2,1.2))
        self.assertFalse(row['heading_valid'])
        self.assertEqual(row['heading_rad'], 0.)

    def test_normalization_and_invalid_input(self):
        row = HorizontalFrame().update([0,0,0], [0,0,10,10])
        self.assertAlmostEqual(row['heading_rad'], math.pi/2)
        for q in ([0,0,0,0], [0,0,float('nan'),1], [1,2,3]):
            with self.assertRaises(ValueError): HorizontalFrame().update([0,0,0], q)
        with self.assertRaises(ValueError): HorizontalFrame().update([0,float('inf'),0], [0,0,0,1])

    def test_config_rejects_duplicate_frame_parents(self):
        base = json.loads((Path(__file__).parents[1]/'config/sensors.json').read_text())
        for name in ('world', 'swing_coordinate', '/bad'):
            with tempfile.TemporaryDirectory() as folder:
                base['horizontal_frame'] = name
                p = Path(folder)/'config.json'; p.write_text(json.dumps(base))
                with self.assertRaises(ValueError): load_config(p)
        base['horizontal_frame'] = 'swing_horizontal_coordinate'
        base['sensors'] = [{'id':'test','topic':'/test','prim_path':'/test',
                            'frame_id':'swing_horizontal_coordinate'}]
        with self.assertRaises(ValueError): validate_sensors(base)


if __name__ == '__main__':
    unittest.main()
