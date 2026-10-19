import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer.unified_bag import camera_id,rigid_pose,calibration_values,committed_groups,contained
from sensor_visualizer.performance import Performance


class UnifiedTests(unittest.TestCase):
    def test_optical_180_rotation_and_translation(self):
        matrix=np.diag([1.,-1.,-1.,1.]);matrix[3,:3]=[1.,2.,3.]
        p,q=rigid_pose(matrix)
        np.testing.assert_allclose(p,[1,2,3]);np.testing.assert_allclose(np.abs(q),[1,0,0,0],atol=1e-8)

    def test_row_vector_yaw_sign(self):
        matrix=np.eye(4);matrix[:3,:3]=[[0,1,0],[-1,0,0],[0,0,1]]
        _,q=rigid_pose(matrix)
        np.testing.assert_allclose(q,[0,0,2**-.5,2**-.5],atol=1e-8)

    def test_scale_not_silently_exported(self):
        matrix=np.diag([2.,1.,1.,1.])
        with self.assertRaises(ValueError):rigid_pose(matrix)

    def test_calibration_preserves_four_coefficients(self):
        k,d=calibration_values(dict(model='opencv_fisheye',width=1920,height=1080,
            intrinsics=dict(fx=500.,fy=510.,cx=959.,cy=539.,k1=.1,k2=.2,k3=.3,k4=.4)))
        self.assertEqual(d,[.1,.2,.3,.4]);self.assertEqual(k,[500.,0.,959.,0.,510.,539.,0.,0.,1.])

    def test_legacy_name_and_traversal(self):
        self.assertEqual(camera_id('rear'),'back')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):contained(Path(folder),'../outside.png')

    def test_committed_image_pose_time_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);camera=root/'cameras/rear';camera.mkdir(parents=True)
            (camera/'frames.jsonl').write_text(json.dumps(dict(simulation_time_ns=200,frame_index=0,image='images/a.png'))+'\n')
            (root/'capture_index.jsonl').write_text(json.dumps(dict(simulation_time_ns=100,cameras={'rear':dict(
                frame_metadata='cameras/rear/frames.jsonl',frame_index=0,image='cameras/rear/images/a.png')}))+'\n')
            with self.assertRaises(ValueError):list(committed_groups(root))

    def test_monitor_flushes_and_keeps_pauses_out_of_rtf(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor=Performance(Path(__file__).resolve().parents[1],folder)
            with monitor.span('encoding'):time.sleep(.001)
            monitor.update(10.,False,'ready');monitor.update(10.,True,'playing')
            monitor.update(10.1,True,'recording');monitor.update(10.1,False,'paused')
            monitor.close()
            report=json.loads((monitor.directory/'summary.json').read_text())
            self.assertEqual(report['spans']['encoding']['count'],1)
            self.assertAlmostEqual(report['state']['active_simulation_s'],.1)
            self.assertEqual(report['dropped_telemetry_events'],0)
            self.assertIsNone(report['error'])


if __name__=='__main__':unittest.main()
