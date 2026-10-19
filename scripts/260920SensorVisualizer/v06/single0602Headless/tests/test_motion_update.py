import unittest
import numpy as np
from single0602_headless.robot.motion_update import MotionUpdateCache
class CacheTests(unittest.TestCase):
    def test_only_unchanged_clock_and_exact_pose_can_reuse(self):
        c=MotionUpdateCache();p=[1,2,3];q=[1,0,0,0];angles=[0,1]
        self.assertEqual(c.changes(p,q,angles,1),(True,True,True));c.commit(p,q,angles,1)
        self.assertEqual(c.changes(p,q,angles,1),(False,False,False))
        self.assertEqual(c.changes(p,q,[0,1.00000001],1),(False,True,False))
        self.assertEqual(c.changes([1,2,3.00000001],q,angles,1),(True,False,False))
        self.assertEqual(c.changes(p,q,angles,2),(True,True,True))
        c.invalidate();self.assertEqual(c.changes(p,q,angles,2),(True,True,True))
    def test_caller_arrays_never_alias_the_cache(self):
        c=MotionUpdateCache();p=np.ones(3);q=np.array([1.,0,0,0]);a=np.ones(2)
        c.commit(p,q,a,1);p[:]=0;a[:]=0
        self.assertEqual(c.changes(p,q,a,1),(True,True,False))
