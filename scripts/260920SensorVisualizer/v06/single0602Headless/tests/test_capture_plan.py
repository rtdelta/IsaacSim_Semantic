import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError
from urllib.parse import urlencode

from single0602_headless.capture_plan import make_plan, source_time_valid, verify_plan
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.contracts import DEFAULT, load_job
from single0602_headless.replay_capture import ReplayCapture
from single0602_headless.trajectory import TrajectoryRecorder
from single0602_headless.web_service import WebService, make_server
from test_contract_and_input import metadata, state

ROOT=Path(__file__).resolve().parents[1]


def recorded(path, duration=.25):
    meta=metadata();meta.update(scene=DEFAULT['scene'],asset_manifest={'test_fixture':True})
    recorder=TrajectoryRecorder(path,meta)
    recorder.append(state(0));recorder.append(state(duration,1));recorder.close()
    return path


class PlanTests(unittest.TestCase):
    def test_grid_edges_and_tail(self):
        for duration,count in [(26.5,266),(26.53,266),(26.499999999999993,266),(.05,1),(0,1),(.3-2e-8,3),(.3-5e-9,4)]:
            with self.subTest(duration=duration):
                plan=make_plan(duration,{'capture_scope':'full_trajectory','sample_hz':10})
                self.assertEqual(plan['planned_groups'],count)
                self.assertTrue(source_time_valid(count-1,duration,10))
                self.assertFalse(source_time_valid(count,duration,10))
        self.assertAlmostEqual(make_plan(26.53,{'capture_scope':'full_trajectory'})['unsampled_tail_s'],.03)

    def test_limits_and_legacy_default(self):
        for requested,count in [(2,2),(3,3),(100,3)]:
            self.assertEqual(make_plan(.25,{'groups':requested})['planned_groups'],count)
        self.assertEqual(make_plan(50,{})['planned_groups'],100)
        self.assertEqual(make_plan(1,{'capture_scope':'full_trajectory','sample_hz':20})['planned_groups'],21)

    def test_invalid_request_and_duration(self):
        bad=[{'capture_scope':'bad'},{'capture_scope':'full_trajectory','groups':1},{'capture_scope':'group_limit'}]
        bad += [{'groups':x} for x in [True,0,-1,1.2,'2',None]]
        bad += [{'sample_hz':x} for x in [0,-1,7,61,True,float('nan'),float('inf')]]
        for payload in bad:
            with self.subTest(payload=payload),self.assertRaises(ValueError):make_plan(1,payload)
        for duration in [-1,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):make_plan(duration,{})

    def test_job_plan_and_snapshot_mismatch(self):
        plan=make_plan(.25,{'capture_scope':'full_trajectory'})
        self.assertEqual(load_job(overrides={'groups':3,'capture_plan':plan})['groups'],3)
        self.assertEqual(load_job()['groups'],100)
        with self.assertRaises(ValueError):verify_plan(plan,.35,3,10)
        with self.assertRaises(ValueError):load_job(overrides={'groups':2,'capture_plan':plan})
        changed=deepcopy(plan);changed['last_sample_time_s']=.25
        with self.assertRaises(ValueError):verify_plan(changed,.25,3,10)

    def test_cli_scope_and_legacy(self):
        import run_capture
        for flags,scope,count in [([], 'group_limit',100),(['--groups','2'],'group_limit',2),(['--all-trajectory'],'full_trajectory',None)]:
            with patch.object(sys,'argv',['run_capture.py','--trajectory','/example']+flags),patch.object(CaptureSupervisor,'start',return_value={}) as start:
                run_capture.launch()
                payload=start.call_args.args[0]
                self.assertEqual(payload['capture_scope'],scope);self.assertEqual(payload.get('groups'),count)
        result=subprocess.run([sys.executable,str(ROOT/'run_capture.py'),'--trajectory','/example','--all-trajectory','--groups','2'],capture_output=True)
        self.assertEqual(result.returncode,2)

    def test_http_preview_is_read_only_and_owner_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);path=recorded(out/'trajectories/test')
            service=WebService(ROOT,out,out/'absent.sock');server=make_server(service,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            opener=build_opener(ProxyHandler({}));base='http://127.0.0.1:'+str(server.server_address[1])
            try:
                query=urlencode({'trajectory':str(path),'capture_scope':'full_trajectory','sample_hz':10})
                with patch('single0602_headless.capture_supervisor.subprocess.Popen') as spawn:
                    value=json.load(opener.open(base+'/api/capture_plan?'+query))
                    self.assertEqual(value['capture_plan']['planned_groups'],3);spawn.assert_not_called()
                self.assertFalse((out/'tasks').exists());self.assertFalse((out/'runtime').exists())
                query=urlencode({'trajectory':str(path),'capture_scope':'group_limit','groups':'2.5'})
                with self.assertRaises(HTTPError):opener.open(base+'/api/capture_plan?'+query)
                with self.assertRaises(ValueError):service.supervisor.preview({'trajectory':str(out.parent)})
                meta=json.loads((path/'metadata.json').read_text());meta['recording_complete']=False
                (path/'metadata.json').write_text(json.dumps(meta))
                with self.assertRaises(ValueError):service.supervisor.preview({'trajectory':str(path)})
            finally:
                service.closed=True;server.shutdown();server.server_close();thread.join(2)

    @unittest.skipIf(os.name=='nt','Linux capture lease')
    def test_final_plan_uses_snapshot_and_recovers_without_status_file(self):
        from single0602_headless.offline_job import snapshot_trajectory
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);source=recorded(out/'trajectories/source',.25)
            replacement=recorded(out/'trajectories/replacement',.35)
            supervisor=CaptureSupervisor(ROOT,out,out/'absent.sock')
            payload={'trajectory':str(source),'capture_scope':'full_trajectory'}
            self.assertEqual(supervisor.preview(payload)['capture_plan']['planned_groups'],3)
            process=Mock(pid=99999999);process.poll.return_value=None
            with patch('single0602_headless.capture_supervisor.snapshot_trajectory',side_effect=lambda src,dst:snapshot_trajectory(replacement,dst)),patch('single0602_headless.capture_supervisor.subprocess.Popen',return_value=process):
                info=supervisor.start(payload)
            self.assertEqual(info['capture_plan']['planned_groups'],4)
            job=json.loads((Path(info['directory'])/'job.json').read_text())
            self.assertEqual(job['groups'],4)
            recovered=CaptureSupervisor(ROOT,out,out/'absent.sock').status()[0]
            self.assertEqual(recovered['capture_plan'],info['capture_plan']);self.assertEqual(recovered['planned_groups'],4)

    @unittest.skipIf(os.name=='nt','Linux capture lease')
    def test_launch_failure_records_error_and_releases_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);source=recorded(out/'trajectories/source')
            supervisor=CaptureSupervisor(ROOT,out,out/'absent.sock')
            with patch('single0602_headless.capture_supervisor.subprocess.Popen',side_effect=OSError('test launch failure')):
                with self.assertRaises(OSError):supervisor.start({'trajectory':str(source),'capture_scope':'full_trajectory'})
            self.assertFalse(supervisor.resource_busy());self.assertEqual(supervisor.tasks,{})
            status=json.loads(next((out/'tasks').glob('*/status.json')).read_text())
            self.assertEqual(status['completion_reason'],'failed');self.assertIn('test launch failure',status['error'])


class ReplayPlanTests(unittest.TestCase):
    def run_capture(self,scenario):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=recorded(root/'trajectory',.25)
            plan=make_plan(.25,{'capture_scope':'full_trajectory'})
            job=load_job(overrides={'output_directory':str(root),'groups':3,'capture_plan':plan,
                'replay':{'mode':'offline','trajectory':str(path),'control_path':str(root/'control.json'),'status_path':str(root/'status.json')}})
            scene=NS(app=Mock(),native_time=lambda:scene.time,time=0.,registry={},render_actual={},asset_manifest={},
                     initialize=AsyncMock(),close=AsyncMock(),apply_snapshot=Mock(),
                     drivers=NS(resource_policy=None,set_capture_active=Mock(),finish_generation=AsyncMock()),
                     motion=NS(snapshot=lambda t:{'swing_zero_readback':{}},config={'swing_zero_mapping':{}}))
            async def advance(t):scene.time=t
            scene.advance_clock=advance;scene.capture=AsyncMock(side_effect=lambda *args:({},{}))
            pipeline=NS(written=0,start=AsyncMock(),reserve=AsyncMock(return_value=0),close=AsyncMock(),poll=Mock())
            async def submit(*args):pipeline.written+=1
            pipeline.submit=submit
            async def finish():
                if scenario=='write_mismatch':pipeline.written=0
            pipeline.finish=finish
            with patch('single0602_headless.replay_capture.SceneStepper',return_value=scene),patch('single0602_headless.replay_capture.RecordPipeline',return_value=pipeline),patch('single0602_headless.replay_capture.verify_replay_identity'),patch('single0602_headless.replay_capture.RunDiagnostics'):
                replay=ReplayCapture(ROOT,job)
                paused=[False]
                def control():
                    if scenario=='stop' and replay.groups==1:return 'stop'
                    if scenario=='late_stop' and replay.groups==3:return 'stop'
                    if scenario=='pause' and replay.groups==1 and not paused[0]:paused[0]=True;return 'pause'
                    return 'run'
                replay.control_state=control
                if scenario=='source_exhausted':replay.source=AsyncMock(return_value=None)
                code=asyncio.run(replay.run())
                return code,json.loads((root/'status.json').read_text()),scene.apply_snapshot.call_count,paused[0]

    def test_all_grids_and_late_stop(self):
        for scenario in ('normal','late_stop','pause'):
            code,result,count,paused=self.run_capture(scenario)
            self.assertEqual(code,0);self.assertEqual(count,3)
            self.assertEqual(result['completion_reason'],'completed_plan');self.assertFalse(result['stopped'])
            self.assertTrue(result['record_drain_complete']);self.assertTrue(result['capture_complete'])
            self.assertEqual(result['written'],3)
            if scenario=='pause':self.assertTrue(paused)

    def test_partial_stop(self):
        code,result,count,_=self.run_capture('stop')
        self.assertEqual(code,0);self.assertEqual(count,1)
        self.assertEqual(result['completion_reason'],'stopped_by_user');self.assertFalse(result['capture_complete'])
        self.assertTrue(result['record_drain_complete']);self.assertEqual(result['written'],1)

    def test_source_or_writer_failure_is_not_complete(self):
        for scenario in ('source_exhausted','write_mismatch'):
            code,result,_,_=self.run_capture(scenario)
            self.assertEqual(code,1);self.assertEqual(result['state'],'failed');self.assertEqual(result['completion_reason'],'failed')
            self.assertFalse(result.get('record_drain_complete',False))
            self.assertIn('exhausted' if scenario=='source_exhausted' else 'Written group count',result['error'])


if __name__=='__main__':unittest.main()
