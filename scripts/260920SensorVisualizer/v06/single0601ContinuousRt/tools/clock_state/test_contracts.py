"""Independent failure injection and analytic-room controls (no SDK needed)."""
import copy,math,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from tools.clock_state.raw_tap import capture,associate
from tools.clock_state.candidates import candidates,classify,group_candidates
from tools.experiments.analyze_mechanism_relations import ray_ranges
from tools.experiments.storage import EvidenceWriter,rows,verify
from single0601_continuous_rt.state_ledger import StateLedger
from tools.clock_state.common import target_table


def pose(p,yaw):
    # Independent trigonometric matrix, not candidate-generation helpers.
    c,s=math.cos(yaw),math.sin(yaw)
    return np.array([[c,s,0,0],[-s,c,0,0],[0,0,1,0],[*p,1.]])


class Contracts(unittest.TestCase):
    def raw_case(self,mapper,with_state=True,source=1.):
        with tempfile.TemporaryDirectory() as td:
            sink=EvidenceWriter(Path(td),1024*1024,2*1024*1024);array=np.array([[1,2,3]],dtype=np.float32)
            data={'ReferenceTime':{'referenceTimeNumerator':60,'referenceTimeDenominator':60},
                'IsaacReadSimulationTime':{'simulationTime':source},
                'IsaacExtractRTXSensorPointCloud':{'data':array,'info':{'transform':np.eye(4)}},
                'GenericModelOutput':np.zeros(264,dtype=np.uint8)}
            writer=SimpleNamespace(entry={'sensor_id':'lidar/test'},kind='lidar',product_path='/product')
            row=capture(data,writer,0,sink,{'source_epoch':'test'});array[:]=99
            ledger=StateLedger()
            if with_state:ledger.publish({'epoch_id':'test','physical_step':60,'sim_time_ns':'1000000000'})
            result=associate(row,mapper,ledger);sink.close();verify(Path(td))
            self.assertTrue((Path(td)/row['payload_path']).is_file());self.assertTrue((Path(td)/row['native_event']['packet_path']).is_file())
            np.testing.assert_array_equal(np.fromfile(Path(td)/row['payload_path'],dtype='<f4'),[1,2,3])
            self.assertEqual(len(rows(Path(td)/'raw_receipts.jsonl')),1)
            return result
    def test_reference_conflict_retains_owned_payload(self):
        r=self.raw_case(lambda ref:2.)
        self.assertTrue(r['formal_event_rejected']);self.assertFalse(r['clock_mapping_ok']);self.assertIsNone(r['physical_step'])
    def test_mapping_exception_retains_owned_payload(self):
        def fail(ref):raise ValueError('injected mapping failure')
        r=self.raw_case(fail);self.assertTrue(r['formal_event_rejected']);self.assertIsNone(r['clock_mapping_ok'])
    def test_missing_ledger_retains_owned_payload(self):
        r=self.raw_case(lambda ref:1.,False);self.assertTrue(r['formal_event_rejected']);self.assertIsNone(r['physical_step'])
    def test_invalid_source_preserves_other_fields(self):
        r=self.raw_case(lambda ref:1.,source=float('nan'));self.assertTrue(r['formal_event_rejected'])
    def test_nonfinite_mapped_time_does_not_abort_diagnostics(self):
        r=self.raw_case(lambda ref:float('nan'));self.assertTrue(r['formal_event_rejected']);self.assertIsNone(r['clock_mapping_ok'])
    def test_epoch_collision_never_matches_current_epoch(self):
        ledger=StateLedger();ledger.publish({'epoch_id':'new','physical_step':60,'sim_time_ns':'1000000000'})
        row={'source_epoch':'old','copy_errors':[],'product_path':'/product','IsaacReadSimulationTime':{'simulationTime':1.},
            'ReferenceTime':{'referenceTimeNumerator':60,'referenceTimeDenominator':60}}
        r=associate(row,lambda ref:1.,ledger);self.assertTrue(r['formal_event_rejected']);self.assertIsNone(r['physical_step'])
    def test_duplicate_simulation_time_is_not_nearest_assigned(self):
        ledger=StateLedger()
        for step in (60,61):ledger.publish({'epoch_id':'same','physical_step':step,'sim_time_ns':'1000000000'})
        row={'source_epoch':'same','copy_errors':[],'product_path':'/product','IsaacReadSimulationTime':{'simulationTime':1.},
            'ReferenceTime':{'referenceTimeNumerator':60,'referenceTimeDenominator':60}}
        r=associate(row,lambda ref:1.,ledger);self.assertTrue(r['formal_event_rejected']);self.assertIsNone(r['physical_step'])
    def test_static_one_equivalence_class_unobservable(self):
        p=pose([0,0,0],0);values=candidates(p,p,p);r=classify(values,{k:1e-7 for k in values})
        self.assertEqual(r['status'],'unobservable');self.assertEqual(len(r['groups']),1)
    def test_pure_rotation_position_delay_unidentifiable(self):
        values=candidates(pose([0,0,0],.02),pose([0,0,0],.01),pose([0,0,0],0))
        residuals={k:(1e-7 if v['r_lag_steps']==1 else .001) for k,v in values.items()};r=classify(values,residuals)
        self.assertEqual(r['status'],'distinguishable');self.assertFalse(r['position_delay_identifiable']);self.assertTrue(r['rotation_delay_identifiable'])
    def test_complete_link_does_not_chain(self):
        values={k:{'matrix':pose([x,0,0],0)} for k,x in [('a',0),('b',.75e-8),('c',1.5e-8)]}
        self.assertEqual(group_candidates(values),[['a','b'],['c']])
    def test_equal_prediction_distinct_poses_is_ambiguous(self):
        values=candidates(pose([.1,0,0],.02),pose([.05,0,0],.01),pose([0,0,0],0))
        self.assertEqual(classify(values,{k:1e-7 for k in values})['status'],'ambiguous')
    def test_missing_candidate_never_excluded(self):
        values=candidates(pose([0,0,0],.02),pose([0,0,0],.01))
        self.assertEqual(classify(values,{k:1e-7 for k in values})['status'],'incomplete_candidates')
    def test_nonrigid_pose_rejected(self):
        p=np.eye(4);p[0,0]=1.001
        with self.assertRaises(ValueError):candidates(p)
    def test_hold_last_tick_and_two_write_policies_same_pose(self):
        for pattern,nmove in [('HOLD1',5),('HOLD2',4),('HOLD3',3),('HOLD_ALT',3)]:
            spec={'physics_hz':60,'stride':6,'speed_m_s':.3,'yaw_rate_deg_s':3.,'hold_pattern':pattern}
            a=target_table(dict(spec,hold_write_policy='WRITE_SAME'),1,12);b=target_table(dict(spec,hold_write_policy='SKIP_WRITE'),1,12)
            for step in a:
                np.testing.assert_array_equal(a[step]['matrix'],b[step]['matrix'])
                if a[step]['hold']:np.testing.assert_array_equal(a[step]['matrix'],a[step-1]['matrix'])
            self.assertTrue(a[6]['hold']);self.assertTrue(a[12]['hold'])
            self.assertAlmostEqual(a[6]['orientation_xyzw'][2],math.sin(math.radians(nmove*.05)/2))
    def test_lossless_gmo_storage_retains_original_bytes_and_hash(self):
        import hashlib
        from tools.clock_state.analyze import packet_bytes
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);sink=EvidenceWriter(p,1024*1024,2*1024*1024,compress_gmo=True)
            data=np.arange(80000,dtype=np.uint8);original=data.tobytes();name=sink.payload('trace_samples/gmo_000001.bin',data)
            sink.close();verify(p);self.assertTrue(name.endswith('.bin.gz'))
            self.assertEqual(packet_bytes(p,{'packet_path':name,'packet_sha256':hashlib.sha256(original).hexdigest()}),original)
    def test_partition_quantiles_equal_nearest_rank_sort(self):
        from tools.clock_state.analyze import quantiles
        from tools.experiments.compare_paired_outputs import quantiles as sorted_quantiles
        for values in ([],[1.],[1.,2.,2.,3.,float('nan')],np.random.default_rng(123).normal(size=12001)):
            self.assertEqual(quantiles(values),sorted_quantiles(values))
    def test_independent_ray_generator_recovers_component_lag(self):
        angles=np.linspace(-math.pi,math.pi,1001);directions=np.column_stack((np.cos(angles),np.sin(angles),np.zeros(len(angles))))
        walls=[{'axis':0,'coordinate_m':10.},{'axis':0,'coordinate_m':-7.},{'axis':1,'coordinate_m':8.},{'axis':1,'coordinate_m':-11.}]
        current=pose([.2,.1,0],.02);old1=pose([.15,.07,0],.01);old2=pose([.1,.04,0],0)
        values=candidates(current,old1,old2)
        for lag,yaw in [(0,.02),(.5,.015),(1,.01),(2,0.)]:
            # Separate 2D slab intersections; no ray_ranges or candidate matrix used for data generation.
            dx=np.cos(angles+yaw);dy=np.sin(angles+yaw)
            with np.errstate(divide='ignore',invalid='ignore'):
                rx=np.where(dx>0,(10-.2)/dx,(-7-.2)/dx);ry=np.where(dy>0,(8-.1)/dy,(-11-.1)/dy)
            observed=np.minimum(rx,ry)
            residuals={k:float(np.quantile(np.abs(ray_ranges(directions,v['matrix'],walls)-observed),.95)) for k,v in values.items()}
            r=classify(values,residuals);self.assertEqual(r['status'],'distinguishable');self.assertEqual(r['rotation_lag_steps'],[lag]);self.assertEqual(r['position_lag_steps'],[0.])


if __name__=='__main__':unittest.main()
