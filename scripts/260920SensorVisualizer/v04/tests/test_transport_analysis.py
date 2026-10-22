import asyncio
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v04.buffers import SlotPool,receive_message,array_view
from sensor_visualizer_v04.pipeline import RecordPipeline
from sensor_visualizer_v04.diagnostics import RunDiagnostics
from sensor_visualizer_v04.contracts import load_job
from sensor_visualizer_v04.analysis import analyze


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_owned_payload_pack_is_off_loop_and_ack_generation_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipe=RecordPipeline(tmp,tmp,load_job(),{}, {},'capture')
            pipe.pool=SlotPool(Path(tmp)/'slots',1,1024)
            pipe.conn,reader=socket.socketpair()
            slot=pipe.pool.reserve(0);array=np.arange(9,dtype=np.float32).reshape(3,3)
            bundle={'group_id':0,'capture_id':'capture'}
            task=asyncio.create_task(asyncio.to_thread(receive_message,reader))
            await pipe.submit(slot,{'lidar/test':array},bundle)
            message=await task
            self.assertFalse(array.flags.writeable)
            descriptor=message['bundle']['buffer'];self.assertEqual(pipe.pool.states[slot],'SENT')
            v=array_view(pipe.pool.maps[slot],descriptor['arrays']['lidar/test'])
            np.testing.assert_array_equal(v,array);del v
            wrong={'event':'release','capture_id':'wrong','slot':slot,'group_id':0,'generation':descriptor['generation']}
            pipe.received.put(wrong)
            with self.assertRaises(RuntimeError):pipe.poll()
            self.assertIn(slot,pipe.pool.in_use)
            pipe.received.put({**wrong,'capture_id':'capture'});pipe.poll()
            self.assertEqual(pipe.pool.states[slot],'FREE')
            reader.close();await pipe.close()

    async def test_stop_while_waiting_slot_never_reserves_or_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipe=RecordPipeline(tmp,tmp,load_job(),{}, {},'capture')
            pipe.pool=SlotPool(Path(tmp)/'slots',1,1024);pipe.pool.reserve(0)
            self.assertIsNone(await pipe.reserve(1,lambda:True))
            self.assertEqual(list(pipe.pool.in_use.values())[0][0],0)
            await pipe.close()

    async def test_zero_hit_lidar_packet_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            pool=SlotPool(Path(tmp)/'slots',1,1024)
            slot=pool.reserve(0);pool.claim_owned(slot)
            descriptor=pool.pack(slot,{'cloud':np.empty((0,3),dtype='<f4')})
            with self.assertRaises(RuntimeError):pool.release(slot,0,descriptor['generation'])
            pool.mark_sent(slot);pool.release(slot,0,descriptor['generation']);pool.close()

    async def test_trace_is_relative_and_truncated_log_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=RunDiagnostics(tmp,load_job()['diagnostics'])
            d.context(group_id=1,capture_id='capture')
            with d.span('render_wait'):await asyncio.sleep(.001)
            d.warning('source_time_mismatch','bad clock');d.close()
            event_file=next(d.directory.glob('events_*.jsonl'))
            with event_file.open('a') as stream:stream.write('{broken\n')
            report=analyze(d.directory,True)
            self.assertEqual(report['incomplete_lines'],1)
            self.assertEqual(report['unclosed_spans'],0)
            trace=json.loads((d.directory/'trace.json').read_text())
            self.assertTrue(all(abs(e['ts'])<1e9 for e in trace['traceEvents']))
            self.assertTrue(any(e['ph']=='b' for e in trace['traceEvents']))

if __name__=='__main__':unittest.main()
