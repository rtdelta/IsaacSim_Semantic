import socket,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from sensor_visualizer_v06.hot_path_metrics import HotPathMetrics
from sensor_visualizer_v06.control_ipc import ControlEndpoint,request

class HotPathTests(unittest.TestCase):
    def test_nested_wall_and_cpu_measurement_and_bounded_samples(self):
        events=[];m=HotPathMetrics(SimpleNamespace(event=lambda n,**kw:events.append((n,kw))),2)
        for _ in range(520):
            m.begin_frame()
            with m.span('outer'):
                with m.span('inner'):sum(range(100))
            m.finish_frame(session_id='test')
        self.assertEqual(m.counters['inner']['count'],520)
        self.assertEqual(len(m.counters['inner']['recent']),512)
        self.assertGreaterEqual(m.counters['outer']['wall_ns'],m.counters['inner']['wall_ns'])
        self.assertEqual(len([n for n,v in events if n=='interactive_frame']),260)
        self.assertIsNone(m.rows)
    @unittest.skipUnless(hasattr(socket,'AF_UNIX'),'Linux socket')
    def test_snapshot_is_small_owned_generation_and_status_remains_complete(self):
        with tempfile.TemporaryDirectory() as d:
            e=ControlEndpoint(Path(d)/'s')
            try:
                e.publish_owned({'phase':'ready','session_id':'x','heartbeat_ns':1,'capture_snapshot':{'pose':[1]},'large':'retained'})
                snap=request(e.path,{'action':'snapshot'});snap['capture_snapshot']['pose'][0]=99
                self.assertEqual(request(e.path,{'action':'snapshot'})['capture_snapshot']['pose'],[1])
                self.assertNotIn('large',snap);self.assertNotIn('receipts',snap)
                self.assertEqual(request(e.path,{'action':'status'})['large'],'retained')
            finally:e.close()
