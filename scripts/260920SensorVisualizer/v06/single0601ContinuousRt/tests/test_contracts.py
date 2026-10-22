import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
from single0601_continuous_rt.common import ContractError, cjson, digest
from single0601_continuous_rt.config import load, validate, SamplingClock
from single0601_continuous_rt.state_ledger import StateLedger
from single0601_continuous_rt.time_joiner import TimeJoiner, GroupTicket
from single0601_continuous_rt.buffer_pool import BufferPool
from single0601_continuous_rt.geometry import matrix_from_pose, rigid_pose, OPTICAL_TO_USD
from single0601_continuous_rt.validation import column_pose
from single0601_continuous_rt.sensor_backend import pose_error

ROOT=Path(__file__).resolve().parents[1]


class Contracts(unittest.TestCase):
    def setUp(self):
        self.job=load(ROOT/'config/mixed_pair.json')

    def test_rational_clock_no_accumulation(self):
        c=SamplingClock(60,10,900000000)
        self.assertEqual(c.target(0),(6,1000000000))
        self.assertEqual(c.target(9999999),(60000000,1000000900000000))
        self.assertEqual(SamplingClock(60,10).time_ns(1),16666667)

    def test_config_faults(self):
        changes=[('sensors','camera_ids',['front','front']),('sensors','camera_ids',[False]),
                 ('clock','physics_hz',59),('clock','sample_hz',7),
                 ('capture','source_time_tolerance_ns',1000000),('capture','runtime_fallback',True),
                 ('render','formal_subframes',18),('output','image_codec','jpeg'),
                 ('pipeline','max_buffer_bytes',32)]
        for section,key,value in changes:
            job=copy.deepcopy(self.job)
            job[section][key]=value
            with self.subTest(field=key), self.assertRaises(ContractError):
                validate(job)
        for config in ('single_camera','single_lidar','mixed_pair','strict_scene18','benchmark_scene18'):
            load(ROOT/'config'/('%s.json'%config))
        self.job['sensors']={'camera_ids':[],'lidar_ids':[]}
        with self.assertRaises(ContractError):validate(self.job)

    def state(self, step=6):
        return {'epoch_id':'e','scene_generation':'scene','physical_step':step,'sim_time_ns':str(step*1000000000//60),
                'snapshot_monotonic_ns':'1','sensor_world_matrices_usd':{'camera/front':np.eye(4).tolist(),'lidar/front':np.eye(4).tolist()}}

    def receipt(self,sid,time_ns=100000000,numerator='1'):
        return {'sensor_id':sid,'source_time_ns':str(time_ns),'native_ref':{'kind':'rational_time','scope':sid,
                'numerator':numerator,'denominator':'10','event_id':None},'ownership':'owned_cpu',
                'received_monotonic_ns':'2','rendered_to_world':np.eye(4).tolist(),
                'source_time_provenance':{'clock_domain':'physics_simulation','mapping_method':'ReferenceTime lookup'}}

    def joiner(self):
        ledger=StateLedger(4)
        state=self.state()
        ledger.publish(state)
        join=TimeJoiner(ledger,'r','e',['camera/front','lidar/front'],self.job['capture'])
        now=time.monotonic_ns()
        ticket=GroupTicket('r','e','s',0,0,6,'100000000',['camera/front','lidar/front'],0,1,str(now),str(now+10000000000))
        join.reserve(ticket)
        join.publish_state(state)
        return join,ledger,ticket

    def test_immutable_history_and_protection(self):
        ledger=StateLedger(1)
        state=self.state()
        ledger.publish(state)
        state['sim_time_ns']='999'
        self.assertEqual(ledger.get('e',6)['sim_time_ns'],'100000000')
        result=ledger.get('e',6)
        result['sim_time_ns']='444'
        self.assertEqual(ledger.get('e',6)['sim_time_ns'],'100000000')
        ledger.retain('e',6)
        with self.assertRaises(ContractError):ledger.publish(self.state(12))
        ledger.release('e',6)
        ledger.publish(self.state(12))

    def test_out_of_order_duplicate_and_static_new_events(self):
        join,ledger,ticket=self.joiner()
        data=np.array([[1.,2.,3.]],dtype='<f4')
        self.assertEqual(join.receive(self.receipt('lidar/front'),data,'e','scene')[1],'accepted')
        self.assertEqual(join.receive(self.receipt('lidar/front'),data.copy(),'e','scene')[1],'duplicate')
        result,disposition=join.receive(self.receipt('camera/front'),np.ones((2,2,3),dtype=np.uint8),'e','scene')
        self.assertTrue(result['sync_checks']['all_sensors_present'])
        join.finish(6)
        self.assertEqual(ledger.references[('e',6)],0)

    def test_fault_inputs_rejected(self):
        cases=['wrong_epoch','wrong_time','borrowed','pose_rotation','pose_translation','conflicting_duplicate','deadline']
        for case in cases:
            join,ledger,ticket=self.joiner()
            evidence=self.receipt('lidar/front')
            data=np.ones((2,3),dtype='<f4')
            epoch='e'
            if case=='wrong_epoch':epoch='old'
            if case=='wrong_time':evidence['source_time_ns']='116666667'
            if case=='borrowed':data=data.view()
            if case=='pose_translation':evidence['rendered_to_world'][3][0]=.002
            if case=='pose_rotation':evidence['rendered_to_world']=matrix_from_pose([0,0,0],[0,0,np.sin(.001),np.cos(.001)]).tolist()
            if case=='conflicting_duplicate':
                join.receive(evidence,data,'e','scene')
                data=np.zeros((2,3),dtype='<f4')
            if case=='deadline':ticket.deadline_monotonic_ns='1'
            with self.subTest(fault=case), self.assertRaises(ContractError):
                join.receive(evidence,data,epoch,'scene')

    def test_slot_generation_budget_and_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            pool=BufferPool(directory,128,1024,3)
            self.assertEqual(pool.groups,1)
            first=pool.reserve(('r','e',0))
            self.assertIsNone(pool.reserve(('r','e',1)))
            with self.assertRaises(ContractError):pool.store(*first,('r','e',0),{'lidar/x':np.ones((20,3),dtype='<f4')})
            desc=pool.store(*first,('r','e',0),{'lidar/x':np.ones((2,3),dtype='<f4')})
            self.assertEqual(desc['arrays']['lidar/x']['nbytes'],24)
            with self.assertRaises(ContractError):pool.release(first[0],first[1]-1,('r','e',0))
            pool.release(*first,('r','e',0))
            self.assertIsNone(pool.reserve(('r','e',1)))
            pool.written(*first,('r','e',0))
            second=pool.reserve(('r','e',1))
            self.assertGreater(second[1],first[1])
            with self.assertRaises(ContractError):pool.release(*first,('r','e',0))
            pool.release(*second,('r','e',1))
            pool.written(*second,('r','e',1))
            self.assertLessEqual(pool.peak_bytes,1024)
            pool.close()

    def test_nonsymmetric_coordinate_known_vector(self):
        q=[0.,0.,np.sin(np.pi/4),np.cos(np.pi/4)]
        usd=matrix_from_pose([1.,2.,3.],q)
        ros=column_pose([1.,2.,3.],q)
        np.testing.assert_allclose(usd.T,ros,atol=1e-12)
        np.testing.assert_allclose(np.array([1.,0.,0.,1.])@usd,[1.,3.,3.,1.],atol=1e-12)
        pos,rot=rigid_pose(usd)
        np.testing.assert_allclose(pos,[1.,2.,3.])
        self.assertAlmostEqual(abs(np.dot(q,rot)),1.)
        optical=OPTICAL_TO_USD@usd
        np.testing.assert_allclose(np.array([0.,0.,1.,1.])@optical,[1.,2.,2.,1.],atol=1e-12)
        self.assertLess(pose_error(usd,usd)[1],1e-12)

    def test_document_example_state_canonical_vector(self):
        example=json.loads((ROOT/'docs/ImpPlan/examples/expected_output_example.json').read_text(encoding='utf-8'))
        self.assertEqual(digest(example['frame_index']['state']),'14e7b7f5b42435f653c59130b378957f022973f3f0f6fcfe997a3beb254faef8')


if __name__=='__main__':unittest.main()
