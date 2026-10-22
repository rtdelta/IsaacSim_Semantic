"""Checks that can detect misleading experiment evidence without running Kit."""
import hashlib,json,struct,tempfile,unittest
from pathlib import Path
import numpy as np
from tools.experiments.decode_gmo import decode
from tools.experiments.compare_paired_outputs import geometry,quantiles
from tools.experiments.storage import EvidenceWriter,save,verify
from tools.experiments.export_pair_trajectory import export


class AnalysisChecks(unittest.TestCase):
    def test_gmo_serialized_layout_ignores_pointer_addresses_and_preserves_bytes(self):
        raw=bytearray(428);struct.pack_into('<4IQI',raw,0,0x4E474D4F,1,0,0,428,2)
        struct.pack_into('<16f',raw,56,*np.eye(4).ravel())
        for offset in (120,160):struct.pack_into('<Q7f',raw,offset,0,0,0,0,1,0,0,0)
        struct.pack_into('<2I',raw,200,1,1)
        struct.pack_into('<7Q',raw,208,*[2**63+i for i in range(7)])
        for offset,values in [(264,(0,0)),(272,(1,4)),(280,(2,5)),(288,(3,6)),(296,(.5,.6))]:
            struct.pack_into('<2i' if offset==264 else '<2f',raw,offset,*values)
        raw[304:306]=bytes([64,0]);struct.pack_into('<IfI',raw,312,1,0,103)
        struct.pack_into('<6I4B',raw,400,10,20,10,20,0,0,0,0,0,0)
        before=hashlib.sha256(raw).hexdigest();header,arrays,aux,xyz=decode(raw)
        np.testing.assert_array_equal(xyz,[[1,2,3],[4,5,6]])
        np.testing.assert_array_equal(arrays['emitter_id'],[10,20]);self.assertEqual(aux['filled_members'],103)
        self.assertEqual(before,hashlib.sha256(raw).hexdigest())
        with self.assertRaises(Exception):decode(raw[:-1])
        raw[4]=2
        with self.assertRaises(Exception):decode(raw)
    def test_geometry_detects_rotation_negative_control(self):
        walls=[{'axis':a,'coordinate_m':v} for a,v in [(0,10),(0,-7),(1,8),(1,-11),(2,6),(2,-4)]]
        points=np.array([[10,3,1],[-7,4,2],[5,8,1],[-4,-11,2]],dtype=float)
        self.assertTrue(geometry(points,np.eye(4),walls)['passes_observable_yaw'])
        theta=.001;wrong=np.eye(4);wrong[:2,:2]=[[np.cos(theta),np.sin(theta)],[-np.sin(theta),np.cos(theta)]]
        result=geometry(points,wrong,walls)
        self.assertFalse(result['passes_observable_yaw']);self.assertAlmostEqual(abs(result['yaw_fit_rad']),theta,places=8)
    def test_missing_actual_target_is_retained_in_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'continuous';directory.mkdir()
            save(directory/'experiment_spec.json',{'targets':3,'stride':6})
            save(directory/'run_result.json',{'source_epoch':'epoch','first_physical_step':12})
            writer=EvidenceWriter(directory,4096,65536)
            for i in (0,2):writer.event('targets.jsonl',{'target_index':i,'physical_step':12+i*6,'actual_state':{'failed_pose':True}})
            writer.close();value=export(directory)
            self.assertEqual(len(value['entries']),3);self.assertIsNone(value['entries'][1]['target'])
            self.assertTrue(value['entries'][0]['target']['actual_state']['failed_pose'])
            (directory/'targets.jsonl').write_text('corrupt')
            with self.assertRaises(ValueError):verify(directory)
    def test_queue_budget_rejects_without_unbounded_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer=EvidenceWriter(tmp,64,10000)
            with self.assertRaises(RuntimeError):writer.payload('too_big.bin',np.zeros(100,dtype=np.uint8))
            self.assertEqual(writer.inflight,0);writer.close()
    def test_nearest_rank(self):
        self.assertEqual(quantiles(range(100))['0.95'],94)


if __name__=='__main__':unittest.main()
