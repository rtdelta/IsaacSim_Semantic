import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v03.sensors import SensorDrivers
from sensor_visualizer_v03.gating import ProductGate
from sensor_visualizer_v03.diagnostics import NullDiagnostics
from sensor_visualizer_v03.tickets import CaptureTicket,SampleError


class Product:
    def __init__(self): self.calls=[]; self.hydra_texture=self
    def set_updates_enabled(self,value): self.calls.append(value)


def ticket(attempt=0):
    return CaptureTicket('run','capture',2,'stage',1_000_000_000,0,frozenset({'cameras/front'}),1,attempt_id=attempt)


class GateTests(unittest.TestCase):
    def test_all_off_and_camera_only_warmup_deduplicates(self):
        gate=ProductGate(); camera,lidar=Product(),Product()
        gate.add('cameras/front',camera); gate.add('lidars/test',lidar)
        gate.all(False,'idle'); gate.kind('cameras',True,'warmup')
        self.assertEqual(camera.calls,[False,True]); self.assertEqual(lidar.calls,[False])
        gate.all(True,'capture');gate.all(False,'movement');gate.all(False,'pause')
        self.assertEqual(camera.calls,[False,True,False]);self.assertEqual(lidar.calls,[False,True,False])
        gate.closed=True
        with self.assertRaises(SampleError):gate.all(True,'bad')

    def test_identity_clock_and_pose_are_independent(self):
        t=ticket();t.submitted=True
        with self.assertRaises(SampleError):t.receive('cameras/front',{},'old_stage',t.request_id)
        t.receive('cameras/front',{},'stage',t.request_id)
        for args in ((999_999_900,0,'serialized_manual_writer'),(1_000_000_000,.003,'serialized_manual_writer'),
                     (1_000_000_000,0,'request_id_only')):
            with self.assertRaises(SampleError):t.validate('cameras/front',*args)
        t.validate('cameras/front',1_000_000_000,0,'serialized_manual_writer')
        self.assertFalse(t.complete);t.render_complete=True;self.assertTrue(t.complete)
        t.close()
        with self.assertRaises(SampleError):t.receive('cameras/front',{},'stage',t.request_id)


class DriverTests(unittest.IsolatedAsyncioTestCase):
    def setup_driver(self,delay=1,source_time=1.,fail_frozen=False):
        d=SensorDrivers.__new__(SensorDrivers);d.diag=NullDiagnostics();d.generation='stage'
        d.gate=ProductGate();d.gate.add('cameras/front',Product());d.gate.add('lidars/test',Product())
        d.ticket=None;d.inflight=None;d.snapshots={};d.errors={};d.progress=None
        d.registry={'cameras':[{'id':'front','prim_path':'/camera','calibration':{'width':2,'height':2}}],'lidars':[]}
        w=types.SimpleNamespace(kind='cameras',entry=d.registry['cameras'][0],pending=None)
        w.schedule_write=lambda:None;d.writers=[w]
        payload={'rgb':np.zeros((2,2,4),np.uint8),'CameraParams':{'cameraViewTransform':np.eye(4)},
                 'IsaacReadSimulationTime':{'simulationTime':source_time}}
        calls=[];updates=[0]
        async def step_async(**kw):
            calls.append(('render',kw))
            if delay==0:d._receive(w,payload)
        async def drain():calls.append(('drain',{}))
        async def update():
            updates[0]+=1;calls.append(('progress',{}))
            if updates[0]==delay:d._receive(w,payload)
        d.rep=types.SimpleNamespace(orchestrator=types.SimpleNamespace(step_async=step_async,wait_until_complete_async=drain))
        app=types.SimpleNamespace(next_update_async=update)
        def frozen():
            if fail_frozen:raise SampleError('scene_changed_while_frozen','Scene edited')
        return d,w,app,frozen,calls

    def pxr(self):
        class Cache:
            def __init__(self,*a):pass
            def GetLocalToWorldTransform(self,*a):return np.eye(4)
        return types.SimpleNamespace(Usd=types.SimpleNamespace(TimeCode=types.SimpleNamespace(Default=lambda:None)),
                                     UsdGeom=types.SimpleNamespace(XformCache=Cache))

    async def test_late_callback_after_step_return_is_retained_without_retry(self):
        d,w,app,frozen,calls=self.setup_driver(delay=1);d.stage=types.SimpleNamespace(GetPrimAtPath=lambda _:None)
        t=ticket()
        with patch.dict(sys.modules,{'pxr':self.pxr()}):
            arrays,cameras,_=await d.acquire(t,2,app,frozen,3)
        self.assertTrue(t.complete);self.assertFalse(t.open)
        self.assertEqual(len([x for x in calls if x[0]=='render']),1)
        self.assertEqual([x[0] for x in calls],['render','progress','drain'])
        self.assertEqual(cameras['front']['source_time_s'],1)
        self.assertTrue(arrays['camera/front'].flags.owndata)
        self.assertTrue(all(v is False for v in d.gate.requested.values()))

    async def test_missing_callback_cannot_be_reassigned_to_next_request(self):
        d,w,app,frozen,_=self.setup_driver(delay=100);old=ticket()
        with self.assertRaises(SampleError) as exc:await d.acquire(old,2,app,frozen,1)
        self.assertEqual(exc.exception.reason,'capture_ready_timeout');self.assertIs(w.pending,old)
        with self.assertRaises(SampleError):await d.acquire(ticket(1),2,app,frozen,1)
        self.assertTrue(all(v is False for v in d.gate.requested.values()))

    async def test_stale_source_is_rejected_and_not_relabelled(self):
        d,w,app,frozen,_=self.setup_driver(delay=0,source_time=.9);d.stage=types.SimpleNamespace(GetPrimAtPath=lambda _:None)
        with patch.dict(sys.modules,{'pxr':self.pxr()}):
            with self.assertRaises(SampleError) as exc:await d.acquire(ticket(),2,app,frozen,3)
        self.assertEqual(exc.exception.reason,'source_time_mismatch')
        self.assertIsNone(w.pending)

    async def test_scene_change_rejected_and_products_disabled(self):
        d,w,app,frozen,_=self.setup_driver(delay=0,fail_frozen=True)
        with self.assertRaises(SampleError):await d.acquire(ticket(),2,app,frozen,3)
        self.assertTrue(all(v is False for v in d.gate.requested.values()))

    async def test_warmup_never_enables_lidar_or_schedules_writer(self):
        d,w,app,frozen,calls=self.setup_driver()
        await d.warm_cameras(16)
        self.assertIsNone(w.pending)
        self.assertEqual(d.gate.products['lidars/test'].calls,[False])
        self.assertEqual(calls[0][1]['rt_subframes'],16)
        self.assertEqual([x[0] for x in calls],['render','drain'])

    async def test_native_stop_drain_precedes_lidar_read_and_keeps_ticket_open(self):
        d,w,app,frozen,calls=self.setup_driver(delay=0)
        t=ticket()
        def read(_):
            self.assertEqual([x[0] for x in calls],['render','drain'])
            self.assertTrue(t.open);return {},{},{}
        d.read=read
        await d.acquire(t,2,app,frozen,3)
        self.assertFalse(t.open)

    async def test_cancellation_waits_for_native_before_releasing_owner(self):
        d,*_=self.setup_driver();gate=asyncio.Event();done=[]
        async def native():await gate.wait();done.append(True)
        task=asyncio.create_task(d._native(native(),'test_native'))
        await asyncio.sleep(0);task.cancel();await asyncio.sleep(0)
        self.assertFalse(task.done());self.assertIsNotNone(d.inflight)
        gate.set()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(done,[True]);self.assertIsNone(d.inflight)

if __name__=='__main__':unittest.main()
