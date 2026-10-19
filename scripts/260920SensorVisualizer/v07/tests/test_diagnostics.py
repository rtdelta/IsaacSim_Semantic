import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v07.contracts import load_job
from sensor_visualizer_v07.diagnostics import RunDiagnostics,redact


class DiagnosticsTests(unittest.TestCase):
    def test_multithread_events_spans_warning_aggregation_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=RunDiagnostics(tmp,load_job()['diagnostics'])
            d.context(capture_id='session',group_id=4)
            def worker():
                for i in range(30):
                    with d.span('encode',sensor_id='front'):pass
            threads=[threading.Thread(target=worker) for _ in range(3)]
            for t in threads:t.start()
            for t in threads:t.join()
            for _ in range(20):d.warning('warning','test warning')
            d.close()
            rows=[json.loads(l) for p in d.directory.glob('events_*.jsonl') for l in p.read_text().splitlines()]
            seq=[r['event_seq'] for r in rows];self.assertEqual(len(seq),len(set(seq)))
            ends=[r for r in rows if r['event']=='span_end'];self.assertEqual(len(ends),90)
            self.assertTrue(all(r['capture_id']=='session' and r['group_id']==4 for r in ends))
            warnings=json.loads((d.directory/'warnings.json').read_text());self.assertEqual(warnings[0]['count'],20)
            summary=json.loads((d.directory/'summary.json').read_text());self.assertEqual(summary['spans']['encode']['count'],90)
            self.assertEqual(summary['state'],'closed')
            self.assertTrue(all(r['thread_cpu_duration_ns']>=0 for r in ends))

    def test_cross_thread_span_never_fabricates_thread_cpu_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=RunDiagnostics(tmp,load_job()['diagnostics'])
            span=d.begin('cross_thread')
            worker=threading.Thread(target=lambda:d.end(span))
            worker.start();worker.join();d.close()
            rows=[json.loads(l) for p in d.directory.glob('events_*.jsonl') for l in p.read_text().splitlines()]
            end=next(r for r in rows if r['event']=='span_end')
            self.assertIsNone(end['thread_cpu_duration_ns'])

    def test_queue_overflow_is_bounded_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_job(overrides={'diagnostics':{'event_queue_capacity':32,'critical_queue_capacity':32}})['diagnostics']
            with patch.object(RunDiagnostics,'_write',lambda self:self.stop.wait(2)):
                d=RunDiagnostics(tmp,cfg)
                for _ in range(300):d.event('fast')
                for _ in range(100):d.event('critical',critical=True)
                self.assertLessEqual(d.queue.qsize(),32);self.assertGreater(d.dropped['normal'],0)
                self.assertGreater(d.dropped['critical'],0);d.close()

    def test_disk_failure_does_not_fail_capture_caller(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_job()['diagnostics']
            with patch.object(RunDiagnostics,'_checkpoint',side_effect=OSError('disk full')):
                d=RunDiagnostics(tmp,cfg);d.event('hello')
                deadline=time.monotonic()+2
                while d.io_error is None and time.monotonic()<deadline:time.sleep(.01)
                self.assertIn('disk full',d.io_error);d.event('still callable');d.close()

    def test_config_and_redaction(self):
        self.assertNotIn('abc123',redact('password=abc123'))
        for overrides in ({'diagnostics':{'level':'wrong'}},{'diagnostics':{'detail_group_range':[10,2]}},
                          {'capture':{'max_retries':-1}}):
            with self.assertRaises(ValueError):load_job(overrides=overrides)

if __name__=='__main__':unittest.main()
