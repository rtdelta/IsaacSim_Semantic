import math, unittest
import numpy as np
from rviz_viewer.model import pose_matrix,matrix_pose,forward_kinematics,deadline_ns,choose_model_group

class ModelTest(unittest.TestCase):
    def test_quaternion_roundtrip_near_half_turn(self):
        q=[math.sin(math.radians(179.9)/2),0,0,math.cos(math.radians(179.9)/2)]
        m=pose_matrix([1,2,3],q);p,actual=matrix_pose(m)
        np.testing.assert_allclose(p,[1,2,3]);np.testing.assert_allclose(pose_matrix(p,actual),m,atol=1e-12)
    def test_joint_pivot_stays_fixed(self):
        parent=np.eye(4);parent[:3,3]=[1,0,0]
        child=np.eye(4);child[:3,3]=[0,0,0]
        manifest={'base_in_reference_col':np.eye(4).tolist(),'joints':[{'name':'boom','axis':'Z','parent':'track_link','child':'boom_link','parent_anchor_col':parent.tolist(),'child_anchor_col':child.tolist()}]}
        body=forward_kinematics(manifest,np.eye(4),{'boom':math.pi/2})['boom_link']
        np.testing.assert_allclose(body@[1,0,0,1],[1,1,0,1],atol=1e-12)
    def test_no_deadline_drift_and_no_offset_wrap(self):
        self.assertEqual(deadline_ns(0,299,10),29_900_000_000)
        self.assertEqual(choose_model_group(10,-1,300),9)
        with self.assertRaises(ValueError):choose_model_group(0,-1,300)
    def test_reject_scale_in_marker_pose(self):
        m=np.diag([2,2,2,1])
        with self.assertRaises(ValueError):matrix_pose(m)

if __name__=='__main__':unittest.main()
