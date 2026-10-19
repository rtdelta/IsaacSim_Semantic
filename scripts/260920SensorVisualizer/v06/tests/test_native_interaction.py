import asyncio
import json
from pathlib import Path
import queue
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import AsyncMock,Mock,patch

from sensor_visualizer_v06.keyboard_control import KeyboardControl
from sensor_visualizer_v06.native_keyboard import NativeKeyboard
from sensor_visualizer_v06.interaction_log import InteractionLog
from sensor_visualizer_v06.interactive_runtime import InteractiveRuntime
from sensor_visualizer_v06.web_service import WebService

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.keyboard=KeyboardControl();self.context=[True,False,True];self.notifications=[]
        self.adapter=NativeKeyboard(self.keyboard,lambda:tuple(self.context),lambda n,**v:self.notifications.append((n,v)))
    def event(self,kind,key):return self.adapter.handle(NS(type=kind,input=key))
    def test_string_enum_and_release(self):
        self.assertFalse(self.event('KEY_PRESS','w'));self.assertEqual(self.keyboard.pressed(),{'W'})
        self.assertFalse(self.event(NS(name='KEY_RELEASE'),NS(name='W')));self.assertEqual(self.keyboard.pressed(),set())
    def test_character_events_never_access_key_or_drive_motion(self):
        class Character:
            type='CHAR'
            @property
            def input(self):raise AssertionError('Character field must not be parsed as a key')
        self.assertTrue(self.adapter.handle(Character()));self.assertEqual(self.keyboard.pressed(),set())
    def test_focus_blocking_and_pause(self):
        for context in ([False,False,True],[True,True,True],[True,False,False]):
            self.context[:]=context;self.assertTrue(self.event('KEY_PRESS','W'));self.assertEqual(self.keyboard.pressed(),set())
    def test_f8_repeat_is_not_a_second_toggle_and_release_survives_blur(self):
        self.event('KEY_PRESS','F8');self.assertFalse(self.keyboard.enabled)
        self.event('KEY_REPEAT','F8');self.assertFalse(self.keyboard.enabled)
        self.event('KEY_PRESS','F8');self.event('KEY_PRESS','W');self.context[0]=False
        self.assertFalse(self.event('KEY_RELEASE','W'));self.assertEqual(self.keyboard.pressed(),set())
    def test_background_log_flushes_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl';log=InteractionLog(path)
            for i in range(10):log.append({'i':i})
            log.close();self.assertEqual([json.loads(s)['i'] for s in path.read_text().splitlines()],list(range(10)))
            self.assertEqual(log.queue.maxsize,4096)

def runtime():
    r=InteractiveRuntime.__new__(InteractiveRuntime)
    r.busy=r.closed=r.failed=r.playing=False;r.error=None;r.lifecycle='paused';r.time_s=1.;r.revision=3;r.session_id='before'
    r.keyboard=KeyboardControl();r.native_keys=set();r.recorder=None;r.drains=set();r.native=None;r.input_subscription=None
    r.endpoint=NS(commands=queue.Queue(),result=Mock(),close=Mock());r.publish=Mock();r.event=Mock();r._commit=Mock()
    r.scene=NS(motion=NS(reset=Mock(),tick=Mock()),poses=NS(reset=Mock()),native_time=lambda:1.,closed=False,close=AsyncMock())
    return r

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_restore_keeps_controller_and_play_works_again(self):
        r=runtime();r.playing=True;r.command({'action':'stop'})
        self.assertEqual(r.lifecycle,'stopped');self.assertFalse(r.playing);r.scene.close.assert_not_called();r.endpoint.close.assert_not_called()
        r.command({'action':'play'});self.assertTrue(r.playing);self.assertEqual(r.lifecycle,'running')
    async def test_stop_does_not_discard_recording_or_draining(self):
        r=runtime()
        for recorder,drains in ((object(),set()),(None,{object()})):
            r.recorder=recorder;r.drains=drains
            with self.assertRaises(ValueError):r.command({'action':'stop'})
        r.scene.motion.reset.assert_not_called()
    async def test_exit_reinitialize_and_reject_play_while_exited(self):
        r=runtime();r.command({'action':'exit','command_id':'exit'})
        with self.assertRaises(ValueError):r.command({'action':'play'})
        await asyncio.sleep(0);await asyncio.sleep(0)
        self.assertEqual(r.lifecycle,'exited');r.endpoint.close.assert_not_called()
        r.endpoint.commands.put({'action':'play','command_id':'wrong'});r._update(None)
        self.assertEqual(r.endpoint.result.call_args.args[1],'failed')
        async def init(**kw):r.lifecycle='paused';r.busy=False
        r.initialize=AsyncMock(side_effect=init);r.command({'action':'reinitialize','command_id':'reopen'})
        await asyncio.sleep(0);await asyncio.sleep(0);self.assertEqual(r.lifecycle,'paused')
        r.command({'action':'play'});self.assertTrue(r.playing)

class WebGuardTests(unittest.TestCase):
    def test_restore_is_rejected_until_capture_exits(self):
        service=WebService.__new__(WebService);service.socket='unused';service.supervisor=NS(status=lambda:[{'running':True}])
        with patch('sensor_visualizer_v06.web_service.request') as send:
            for action in ('stop','reset','exit','close'):
                with self.assertRaises(ValueError):service.command({'action':action})
            send.assert_not_called()
