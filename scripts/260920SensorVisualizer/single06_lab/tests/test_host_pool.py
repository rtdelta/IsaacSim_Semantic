import asyncio,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'frozen_runtime'))
import numpy as np
from sensor_visualizer_v06.diagnostics import NullDiagnostics
from sensor_visualizer_v06.sensors import SensorDrivers
from sensor_visualizer_v06.pipeline import RecordPipeline
from sensor_visualizer_v06.scene import SceneStepper
from lab.host_pool import HostPool

class PoolContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_buffer_not_reused_until_pack_completed(self):
        entered=asyncio.Event();completed=asyncio.Event()
        async def pack(*args):entered.set();await completed.wait()
        async def capture(*args):return 'ok'
        with patch.object(RecordPipeline,'submit',pack),patch.object(SceneStepper,'capture',capture):
            pool=HostPool();pool.install()
            try:
                d=SensorDrivers();d.diag=NullDiagnostics();p=RecordPipeline.__new__(RecordPipeline);p.diag=d.diag
                first=d._copy_host(np.ones((4,4),dtype='uint8'),'camera/front')
                task=asyncio.create_task(p.submit(0,{},{}));await entered.wait()
                with self.assertRaisesRegex(RuntimeError,'still leased'):await SceneStepper.capture(None,0,0)
                self.assertTrue(pool.leases);completed.set();await task
                self.assertFalse(pool.leases);self.assertEqual(await SceneStepper.capture(None,1,0),'ok')
                second=d._copy_host(np.full((4,4),2,dtype='uint8'),'camera/front')
                self.assertIs(first,second);self.assertTrue(np.all(second==2))
            finally:pool.uninstall()
    async def test_failed_pack_poisons_pool(self):
        async def pack(*args):raise RuntimeError('broken IPC')
        with patch.object(RecordPipeline,'submit',pack):
            pool=HostPool();pool.install()
            try:
                d=SensorDrivers();d.diag=NullDiagnostics();p=RecordPipeline.__new__(RecordPipeline);p.diag=d.diag
                d._copy_host(np.zeros(4),'camera/front')
                with self.assertRaises(RuntimeError):await p.submit(0,{},{});
                with self.assertRaisesRegex(RuntimeError,'poisoned'):d._copy_host(np.ones(4),'camera/front')
            finally:pool.uninstall()
    async def test_variable_shape_reallocates_only_owned_cpu_buffer(self):
        pool=HostPool();pool.install()
        try:
            d=SensorDrivers();d.diag=NullDiagnostics()
            first=d._copy_host(np.zeros((4,3)),'lidar/front');pool.leases.clear()
            second=d._copy_host(np.zeros((6,3)),'lidar/front')
            self.assertIsNot(first,second);self.assertEqual(second.shape,(6,3))
        finally:pool.uninstall()
if __name__=='__main__':unittest.main()
