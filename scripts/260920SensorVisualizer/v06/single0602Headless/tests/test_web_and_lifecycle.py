import asyncio
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import urllib.request
import urllib.error

from single0602_headless.interactive_runtime import InteractiveRuntime
from single0602_headless.keyboard_control import KeyboardControl
from single0602_headless.web_service import WebService, make_server
from single0602_headless.trajectory import TrajectoryRecorder, Trajectory
from single0602_headless.capture_supervisor import CaptureSupervisor
from test_contract_and_input import metadata, state


class WebTests(unittest.TestCase):
    def test_http_receipts_and_complete_zip_roundtrip(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            service=WebService(root,temp,Path(temp)/'absent.sock')
            server=make_server(service,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_address[1])
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                html=opener.open(url).read().decode();self.assertIn('single0602',html)
                self.assertNotIn('value="live_latest"',html)
                self.assertEqual(json.load(opener.open(url+'/api/status'))['engine']['phase'],'disconnected')
                p=Path(temp)/'recorded';rec=TrajectoryRecorder(p,metadata());rec.append(state(0));rec.append(state(1,2));rec.close()
                zipped=service.export(p);imported=service.import_zip(zipped)
                self.assertEqual(Trajectory.load(imported['path']).sample(.5)['position_world_m'][0],1.)
                body=json.dumps({'action':'keyboard','payload':{'enabled':True}}).encode()
                req=urllib.request.Request(url+'/api/command',data=body,headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as err:opener.open(req)
                self.assertEqual(err.exception.code,403)
                req.add_header('X-S0602-Token',service.token)
                with patch('single0602_headless.web_service.request',return_value={'state':'queued','command_id':'one'}):
                    self.assertEqual(json.load(opener.open(req))['state'],'queued')
                with self.assertRaises(ValueError):service.import_trajectory({'states':[state(0)],'metadata':{}})
            finally:
                service.closed=True;server.shutdown();server.server_close();thread.join(timeout=2)

    def test_independent_capture_does_not_block_gui_exit(self):
        service=WebService.__new__(WebService);service.socket='test'
        service.supervisor=NS(status=lambda:[{'running':True}])
        with patch('single0602_headless.web_service.request',return_value={'state':'queued'}) as call:
            for action in ('exit','close','reset','stop'):
                self.assertEqual(service.command({'action':action})['state'],'queued')
            self.assertEqual(call.call_count,4)

    def test_no_live_owner_query_before_rejecting_live_capture(self):
        s=CaptureSupervisor.__new__(CaptureSupervisor);s.lock=threading.Lock();s.tasks={};s.resource_busy=lambda:False
        with patch('single0602_headless.control_ipc.request') as request:
            with self.assertRaises(ValueError):s.start({'mode':'live_complete'})
            request.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def test_mode_and_web_motion_preserve_session_and_clock(self):
        r=InteractiveRuntime.__new__(InteractiveRuntime)
        r.busy=False;r.keyboard=KeyboardControl();r._hold_actual=Mock();r._commit=Mock();r.event=Mock();r.publish=Mock()
        r.revision=3;r.time_s=2.5;r.playing=True;r.session_id='one';r.recorder=object()
        r.binding_pending=False;r.timeline_state='playing'
        r.scene=NS(motion=NS(ready=True),apply_commands=Mock())
        for index in range(20):
            result=r.command({'action':'keyboard','payload':{'enabled':index%2==0}})
            self.assertEqual(result['input_epoch'],index+1)
            self.assertTrue(r.playing);self.assertEqual(r.time_s,2.5);self.assertEqual(r.session_id,'one')
        r.command({'action':'motion','payload':{'base':{'x':2}}})
        self.assertEqual(r.keyboard.reason,'web_motion_command');self.assertEqual(r._commit.call_args.args,('direct',))

    def test_stale_epoch_cannot_resume_after_web_motion(self):
        k=KeyboardControl();k.configure({'enabled':True});old=k.input_epoch
        k.update('web:test',['W'],old,1);k.clear('web_motion_command')
        with self.assertRaises(ValueError):k.update('web:test',['W'],old,2)
        self.assertEqual(k.pressed(),set())

if __name__=='__main__':unittest.main()
