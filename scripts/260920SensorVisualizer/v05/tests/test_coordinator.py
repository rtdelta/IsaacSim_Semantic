import asyncio
from pathlib import Path
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v05.contracts import load_job
from sensor_visualizer_v05.coordinator import CaptureRunner
from sensor_visualizer_v05.diagnostics import RunDiagnostics


class FakePipeline:
    def __init__(self,project,session,job,registry,render,token,diag):
        self.written=0;self.process=types.SimpleNamespace(pid=os.getpid());self.calls=[];self.closed=False
    async def start(self):self.calls.append('start')
    def poll(self):pass
    async def reserve(self,group,cancel=None):return None if cancel and cancel() else group
    async def submit(self,slot,arrays,bundle):self.calls.append(('submit',bundle['group_id']));self.written+=1
    async def finish(self):self.calls.append('finish')
    async def close(self):self.closed=True


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,tmp,fail=False):
        job=load_job(overrides={'output_directory':tmp,'groups':3})
        diag=RunDiagnostics(tmp,job['diagnostics']);trace=[];clock=[0]
        class Scene:
            drivers=types.SimpleNamespace(suspend_all=lambda reason:trace.append(('off',reason)))
            registry={};render_actual={};asset_manifest={};poses=types.SimpleNamespace(snapshot=lambda:[])
            last_capture_timings={};capture_failed=False
            def check_stage(self):pass
            def apply_commands(self,*a):pass
            def native_time(self):return clock[0]
            async def advance(self,group):
                self.on_phase('advancing',{});trace.append(('advance',group));clock[0]=group*.1
            async def capture(self,group,stamp):
                self.on_phase('waiting_data',{'pending':['camera/front']});trace.append(('capture',group))
                if fail and group==1:raise RuntimeError('test capture failure')
                await asyncio.sleep(0)
                return {},{'group_id':group,'simulation_time_ns':stamp}
        scene=Scene();runner=CaptureRunner(tmp,job,scene,diag)
        def update(r):
            if not fail and r.phase=='waiting_data':r.stop()
        runner.on_update=update
        with patch('sensor_visualizer_v05.coordinator.RecordPipeline',FakePipeline):
            result=await runner.run()
        diag.close()
        return result,runner,trace

    async def test_stop_during_readiness_finishes_group_before_drain(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,r,trace=await self.exercise(tmp)
            self.assertEqual(result['state'],'finished');self.assertEqual(result['complete_groups'],1)
            self.assertEqual(r.pipeline.calls,['start',('submit',0),'finish']);self.assertTrue(r.pipeline.closed)
            self.assertEqual([x for x in trace if x[0]=='advance'],[('advance',0)])

    async def test_failure_preserves_prior_group_and_closes_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,r,trace=await self.exercise(tmp,True)
            self.assertEqual(result['state'],'failed');self.assertEqual(result['complete_groups'],1)
            self.assertTrue(result['partial_recording_closed']);self.assertTrue(r.pipeline.closed)
            self.assertNotIn(('submit',1),r.pipeline.calls);self.assertTrue(r.scene.capture_failed)

if __name__=='__main__':unittest.main()
