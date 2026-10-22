import unittest
from sensor_visualizer_v06.contracts import load_job
from sensor_visualizer_v06.internal_scheduling import yield_duration_ms

class SchedulingTests(unittest.TestCase):
    def test_yield_is_only_for_fresh_live_owner_and_bounded(self):
        c={'cooperative_yield_ms':50,'yield_only_with_owner':True};now=4_000_000_000
        self.assertEqual(yield_duration_ms(c,{'phase':'interactive_ready','heartbeat_ns':now},now),50)
        for owner in (None,{'phase':'exited','heartbeat_ns':now},{'phase':'interactive_ready','heartbeat_ns':0},{'phase':'interactive_ready','heartbeat_ns':now+1}):
            self.assertEqual(yield_duration_ms(c,owner,now),0)
        with self.assertRaises(ValueError):load_job(overrides={'scheduling':{'cooperative_yield_ms':101}})
        with self.assertRaises(ValueError):load_job(overrides={'scheduling':{'cpu_nice':-1}})
