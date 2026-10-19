import asyncio,sys,unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'frozen_runtime'))
from sensor_visualizer_v06 import replay_capture as replay
from sensor_visualizer_v06.scene import SceneStepper
from sensor_visualizer_v06.diagnostics import NullDiagnostics
from lab.scene_lease import SceneLease

class SceneLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuse_requires_drained_generation(self):
        diag=NullDiagnostics();job={'scene':'same','render':{},'physics_hz':60,'capture':{}}
        scene=S(closed=False,check_stage=lambda:None,drivers=S(inflight=None,generation_open=False,ticket=None,gate=S(diag=diag)),diag=diag)
        lease=SceneLease();lease.scene=scene
        import json
        lease.key=json.dumps(job,sort_keys=True);lease.install()
        try:
            self.assertIs(replay.SceneStepper(None,job,diag),scene)
            scene.drivers.generation_open=True
            with self.assertRaisesRegex(RuntimeError,'not drained'):replay.SceneStepper(None,job,diag)
            scene.drivers.generation_open=False;scene.drivers.ticket=S(open=True)
            with self.assertRaisesRegex(RuntimeError,'ticket open'):replay.SceneStepper(None,job,diag)
        finally:lease.uninstall()
    async def test_changed_quality_rejected(self):
        diag=NullDiagnostics();job={'scene':'same','render':{},'physics_hz':60,'capture':{}}
        lease=SceneLease();lease.scene=S();lease.key='different';lease.install()
        try:
            with self.assertRaisesRegex(ValueError,'contract changed'):replay.SceneStepper(None,job,diag)
        finally:lease.uninstall()
if __name__=='__main__':unittest.main()
