import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sensor_visualizer_v07.contracts import load_job,publish_new_json
from sensor_visualizer_v07.device_binding import resolve_device,observe_array,canonical_pci,resolve_cuda_ordinal
from sensor_visualizer_v07.capture_service import compatibility_key
from sensor_visualizer_v07.diagnostics import RunDiagnostics
from sensor_visualizer_v07.cpu_budget import read_budget
from sensor_visualizer_v07.interaction_log import InteractionLog
from sensor_visualizer_v07.capture_supervisor import CaptureSupervisor
from sensor_visualizer_v07.control_ipc import ControlEndpoint,request,transport_path
from sensor_visualizer_v07.analysis import analyze
from sensor_visualizer_v07.keyboard_control import KeyboardControl
from sensor_visualizer_v07.robot.joint_control import physx_revolute_limits,bounded_keyboard_angle,JointController

class RuntimeTests(unittest.TestCase):
    def test_gc_observer_accounts_for_pause_and_unsubscribes_on_close(self):
        import gc
        with tempfile.TemporaryDirectory() as tmp:
            diag=RunDiagnostics(tmp,load_job()['diagnostics']);callback=diag.gc_timing.callback
            gc.collect(2);diag.close()
            self.assertNotIn(callback,gc.callbacks)
            summary=json.loads((diag.directory/'summary.json').read_text())
            self.assertGreaterEqual(summary['python_gc']['2']['count'],1)
            self.assertTrue(summary['complete'])
    def test_unbounded_revolute_limits_and_continuous_keys_never_reach_invalid_drive_target(self):
        limits=physx_revolute_limits(float('-inf'),float('inf'))
        controller=JointController({'boom':0},{'boom':limits},{'boom':10})
        state=controller.states['boom']
        for _ in range(100000):state.angle=bounded_keyboard_angle(state.angle,.01,state.lower,state.upper)
        self.assertEqual(state.angle,15)
        with self.assertRaises(ValueError):controller.execute({'boom':{'mode':'direct','target':361}},{'boom':state.angle})
        self.assertEqual(bounded_keyboard_angle(45,-.1,-15,15),44.9)
        self.assertEqual(bounded_keyboard_angle(45,.1,-15,15),45)
        self.assertEqual(bounded_keyboard_angle(-45,.1,-15,15),-44.9)

    def test_input_latency_retains_socket_accept_time_instead_of_handler_time(self):
        keyboard=KeyboardControl();keyboard.update('web',['W'],received_ns=123,command_id='queued-input')
        self.assertEqual(keyboard.received_ns,123);self.assertEqual(keyboard.command_id,'queued-input')

    def test_mailbox_never_overwrites_another_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pending.json'
            publish_new_json(path,{'job_id':'first'})
            with self.assertRaises(FileExistsError):publish_new_json(path,{'job_id':'second'})
            self.assertEqual(json.loads(path.read_text()),{'job_id':'first'})
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])

    def test_physical_identity_ignores_cuda_ordinal_order(self):
        devices=[{'index':0,'uuid':'GPU-A','pci':'0000:34:00.0'},{'index':1,'uuid':'GPU-B','pci':'0000:35:00.0'}]
        self.assertEqual(resolve_device('GPU-B',devices)['index'],1)
        self.assertEqual(canonical_pci('00000000:35:00.0'),'0000:35:00.0')
        binding={'requested':devices[1],'cuda_roster':[{'ordinal':0,'pci':devices[1]['pci']}]}
        self.assertEqual(resolve_cuda_ordinal(devices[1],binding['cuda_roster']),0)
        with self.assertRaises(RuntimeError):resolve_cuda_ordinal(devices[0],binding['cuda_roster'])
        class Device:
            ordinal=0
            def __str__(self):return 'cuda:0'
        class Array:device=Device()
        self.assertEqual(observe_array(Array(),binding)['uuid'],'GPU-B')
        binding['requested']=devices[0]
        with self.assertRaises(RuntimeError):observe_array(Array(),binding)

    def test_scene_reuse_key_excludes_dynamic_pose_but_includes_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'scene.usda';path.write_text('#usda 1.0')
            job=load_job(overrides={'scene':str(path)}) if str(path).startswith('/') else load_job()
            job['scene']=str(path);key=compatibility_key(job)
            job['motion']['base']['x']=99;job['mount_poses']={'sensor':{'position_m':[1,2,3]}}
            self.assertEqual(compatibility_key(job),key)
            job['render']['camera_subframes']+=1
            self.assertNotEqual(compatibility_key(job),key)

    def test_complete_log_accounts_for_every_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            diag=RunDiagnostics(tmp,load_job()['diagnostics'])
            for group in range(3):
                diag.context(worker_id='worker',job_id='job',group_id=group,slot_generation=group+1)
                with diag.span('capture'):diag.event('ready',critical=True)
            diag.close()
            summary=json.loads((diag.directory/'summary.json').read_text())
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['events_generated'],summary['events_written'])
            rows=[json.loads(line) for path in diag.directory.glob('events_*.jsonl') for line in path.read_text().splitlines()]
            self.assertEqual(sorted(row['event_seq'] for row in rows),list(range(1,len(rows)+1)))
            self.assertTrue(all(row['worker_id']=='worker' for row in rows if row['event']=='ready'))
            self.assertEqual(analyze(diag.directory)['log_quality'],[])

    def test_log_analysis_reports_missing_sequence_even_without_explicit_drop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=[{'monotonic_ns':seq,'event':'received','event_seq':seq,'pid':1,'process_role':'isaac','run_id':'test'} for seq in (1,3)]
            (root/'events_isaac_1.jsonl').write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
            result=analyze(root)
            self.assertEqual(result['event_sequences'][0]['missing_before_last_seq'],1)
            self.assertTrue(result['log_quality'])

    def test_cpu_quota_is_not_visible_cpu_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'cpu.max').write_text('2800000 100000')
            budget=read_budget(tmp)
            self.assertEqual(budget['quota_cpu_equivalents'],28)

    def test_control_log_closes_with_accounted_history_across_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'control.jsonl'
            for session in range(2):
                log=InteractionLog(path)
                for seq in range(20):log.append({'event':'applied','command_id':str(seq)})
                log.close();self.assertIsNone(log.error)
                summary=json.loads(path.with_suffix('.summary.json').read_text())
                self.assertTrue(summary['complete']);self.assertEqual(summary['events_written'],20)
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(rows),40)
            self.assertEqual(len({row['control_log_id'] for row in rows}),2)
            self.assertEqual(len(list(Path(tmp).glob('control.*.summary.json'))),2)

    def test_closing_worker_cannot_accept_jobs_before_native_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runtime').mkdir()
            (root/'runtime/capture_launch.json').write_text(json.dumps({'pid':123,'start_ticks':'456'}))
            (root/'runtime/capture_worker_status.json').write_text(json.dumps({'pid':123,'start_ticks':'456','phase':'closed'}))
            supervisor=CaptureSupervisor(root,root,'missing.sock')
            with patch('sensor_visualizer_v07.capture_supervisor.request',side_effect=OSError),patch.object(supervisor,'start_ticks',return_value='456'):
                self.assertEqual(supervisor.worker_status()['phase'],'releasing_worker')

    @unittest.skipUnless(__import__('os').name=='posix','worker launcher uses Linux flock')
    def test_ensure_worker_rejects_closing_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            supervisor=CaptureSupervisor(tmp,tmp,'missing.sock')
            with patch.object(supervisor,'worker_status',return_value={'phase':'releasing_worker'}):
                with self.assertRaisesRegex(ValueError,'closing'):supervisor.ensure_worker()

    @unittest.skipUnless(__import__('os').name=='posix','Linux sockaddr_un fallback')
    def test_deep_output_directory_uses_private_short_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            logical=Path(tmp)/('long_run_directory_'*8)/'capture.sock'
            endpoint=ControlEndpoint(logical)
            try:
                endpoint.publish({'phase':'idle'})
                self.assertLess(len(__import__('os').fsencode(endpoint.path)),104)
                self.assertEqual(request(logical,{'action':'status'})['phase'],'idle')
                with self.assertRaises(RuntimeError):ControlEndpoint(logical)
            finally:endpoint.close()
            self.assertFalse(transport_path(logical).exists())

    @unittest.skipUnless(__import__('os').name=='posix','Linux zombie process state')
    def test_exited_unreaped_worker_does_not_block_next_service(self):
        import os,time
        pid=os.fork()
        if pid==0:os._exit(0)
        try:
            deadline=time.monotonic()+2
            while CaptureSupervisor.start_ticks(pid) is not None and time.monotonic()<deadline:time.sleep(.01)
            self.assertIsNone(CaptureSupervisor.start_ticks(pid))
        finally:os.waitpid(pid,0)

if __name__=='__main__':unittest.main()
