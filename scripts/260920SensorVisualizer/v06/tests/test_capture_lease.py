import json,os,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from sensor_visualizer_v06.capture_supervisor import CaptureSupervisor
from sensor_visualizer_v06.web_service import WebService

class CaptureLeaseTests(unittest.TestCase):
    def test_start_rejects_cleanup_before_source_side_effects(self):
        s=CaptureSupervisor.__new__(CaptureSupervisor);s.lock=threading.Lock();s.tasks={};s.resource_busy=Mock(return_value=True)
        with patch('sensor_visualizer_v06.capture_supervisor.request') as read:
            with self.assertRaisesRegex(ValueError,'releasing'):s.start({'mode':'live_complete'})
            read.assert_not_called()
    def test_recovered_finished_status_distinguishes_pending_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);(directory/'status.json').write_text(json.dumps({'state':'finished','groups':3}))
            s=CaptureSupervisor.__new__(CaptureSupervisor);s.lock=threading.Lock();s.alive=Mock(return_value=False)
            s.resource_busy=Mock(return_value=True);s.tasks={'task':{'pid':1,'process':None,'directory':directory,'mode':'offline','created':'2026'}}
            row=s.status()[0];self.assertFalse(row['running']);self.assertTrue(row['cleanup_pending'])
            self.assertEqual(row['state'],'releasing_resources')
            s.resource_busy.return_value=False;row=s.status()[0]
            self.assertEqual(row['state'],'finished');self.assertFalse(row.get('cleanup_pending',False))
    @unittest.skipUnless(os.name=='posix','Linux inherited flock lease')
    def test_actual_lease_probe_without_changing_lock_file(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp:
            s=CaptureSupervisor.__new__(CaptureSupervisor);s.output=Path(temp)
            self.assertFalse(s.resource_busy());self.assertFalse((s.output/'runtime/capture.lock').exists())
            p=s.output/'runtime/capture.lock';p.parent.mkdir();p.write_bytes(b'')
            with p.open('rb') as held:
                fcntl.flock(held.fileno(),fcntl.LOCK_EX);self.assertTrue(s.resource_busy())
            self.assertFalse(s.resource_busy());self.assertEqual(p.read_bytes(),b'')
    def test_web_restore_is_blocked_during_recovered_cleanup(self):
        service=WebService.__new__(WebService);service.socket='unused'
        service.supervisor=SimpleNamespace(status=lambda:[{'running':False,'cleanup_pending':True}])
        with patch('sensor_visualizer_v06.web_service.request') as send:
            for action in ('stop','reset','exit','close'):
                with self.assertRaises(ValueError):service.command({'action':action})
            send.assert_not_called()
