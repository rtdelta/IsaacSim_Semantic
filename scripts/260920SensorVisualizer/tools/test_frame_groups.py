"""Test real capture failure modes without a renderer."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer.frame_groups import FrameGroups


class FrameGroupTests(unittest.TestCase):
    def test_out_of_order_cameras_share_one_timestamp(self):
        join=FrameGroups(['front','rear','left','right'])
        for cid in ['right','front','left']:
            self.assertEqual(join.add(cid,100,cid),([],[]))
        complete,dropped=join.add('rear',100,'rear')
        self.assertEqual(complete,[(100,dict(front='front',rear='rear',left='left',right='right'))])
        self.assertFalse(dropped)
        self.assertEqual(join.add('rear',100,'duplicate'),([],[]))

    def test_lagged_frame_not_replaced_by_next_frame(self):
        join=FrameGroups(['a','b'])
        join.add('a',100,'a100');join.add('a',200,'a200')
        self.assertEqual(join.add('b',200,'b200'),([],[]))
        complete,_=join.add('b',100,'b100')
        self.assertEqual([t for t,_ in complete],[100,200])
        self.assertEqual(complete[0][1]['b'],'b100')

    def test_missing_camera_does_not_grow_memory_forever(self):
        join=FrameGroups(['a','b'],max_pending=2)
        join.add('a',100,1);join.add('a',200,2)
        complete,dropped=join.add('a',300,3)
        self.assertFalse(complete)
        self.assertEqual(dropped[0]['missing_cameras'],['b'])
        self.assertEqual(len(join.pending),2)
        self.assertEqual(join.add('b',100,'too late'),([],[]))

    def test_stop_saves_complete_trailing_group(self):
        join=FrameGroups(['a','b'])
        join.add('a',100,'a100');join.add('a',200,'a200');join.add('b',200,'b200')
        complete,dropped=join.finish()
        self.assertEqual([t for t,_ in complete],[200])
        self.assertEqual(dropped,[{'simulation_time_ns':100,'missing_cameras':['b'],'reason':'recording_stopped'}])
        self.assertFalse(join.pending)


if __name__=='__main__': unittest.main()
