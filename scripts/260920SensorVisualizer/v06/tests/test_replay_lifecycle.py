import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sensor_visualizer_v06 import replay_capture as replay
from sensor_visualizer_v06.contracts import load_job
from sensor_visualizer_v06.trajectory import TrajectoryRecorder
from test_interaction_trajectory import state

class Diagnostic:
    def __init__(self,*a,**k):pass
    def start_resources(self):pass
    def attach_kit(self,*a):pass
    def detach_kit(self):pass
    def close(self):pass
class Driver:
    resource_policy=None
    def set_capture_active(self,*a):pass
    async def finish_generation(self):pass
class Scene:
    def __init__(self,*a):
        self.app=object();self.drivers=Driver();self.registry={};self.render_actual={};self.asset_manifest={};self.time=1.;self.on_phase=None
    async def initialize(self):pass
    def native_time(self):return self.time
    async def advance_clock(self,t):self.time=1+t
    def apply_snapshot(self,s):pass
    async def capture(self,g,stamp):return {},{'group_id':g,'simulation_time_ns':stamp}
    async def close(self):
        if self.on_phase:self.on_phase('closing',{})
class Pipeline:
    def __init__(self,*a):self.written=0
    async def start(self):pass
    async def reserve(self,*a):return 0
    async def submit(self,*a):self.written+=1
    async def finish(self):pass
    async def close(self):pass
class ReplayTests(unittest.TestCase):
    def test_complete_stream_uses_only_a_small_bracket(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);trajectory=p/'trajectory';r=TrajectoryRecorder(trajectory,{'scene':'/fake.usda'})
            for i in range(1000):r.append(state(i/1000,i))
            r.close()
            job=load_job(overrides={'output_directory':str(p/'output'),'replay':{'mode':'live_complete',
                'trajectory':str(trajectory),'control_path':str(p/'control.json'),'status_path':str(p/'status.json')}})
            with patch.object(replay,'RunDiagnostics',Diagnostic):runtime=replay.ReplayCapture(p,job)
            runtime.feed_offset=0;runtime.feed_rows=[]
            row=asyncio.run(runtime.source(0));self.assertEqual(row['position_world_m'][0],0)
            self.assertLessEqual(len(runtime.feed_rows),2);self.assertLess(runtime.feed_offset,(trajectory/'states.jsonl').stat().st_size/10)
            row=asyncio.run(runtime.source(1));self.assertAlmostEqual(row['position_world_m'][0],100)
            self.assertLessEqual(len(runtime.feed_rows),2)
    def test_final_result_survives_scene_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);trajectory=p/'trajectory';r=TrajectoryRecorder(trajectory,{'scene':'/fake.usda'})
            r.append(state(0));r.append(state(.2,1));r.close()
            job=load_job(overrides={'groups':3,'output_directory':str(p/'output'),
                'replay':{'mode':'offline','trajectory':str(trajectory),'control_path':str(p/'control.json'),'status_path':str(p/'status.json')}})
            with patch.object(replay,'RunDiagnostics',Diagnostic),patch.object(replay,'SceneStepper',Scene),patch.object(replay,'RecordPipeline',Pipeline):
                runtime=replay.ReplayCapture(p,job);self.assertEqual(asyncio.run(runtime.run()),0)
            status=json.loads((p/'status.json').read_text())
            self.assertEqual(status['state'],'finished');self.assertEqual(status['written'],3)
            self.assertEqual(json.loads((runtime.session/'session.json').read_text())['state'],'finished')
    def test_unknown_first_mount_revision_is_rejected(self):
        from sensor_visualizer_v06.trajectory import Trajectory
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'trajectory';r=TrajectoryRecorder(p,{'scene':'/fake.usda'});r.append(state(0));r.close()
            meta=json.loads((p/'metadata.json').read_text());meta['mount_revisions']={'9':state(0)['mounts']}
            with self.assertRaises(ValueError):Trajectory.from_csv((p/'trajectory.csv').read_text(),meta)

if __name__=='__main__':unittest.main()
