from copy import deepcopy
import asyncio
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch

from single0602_headless.scene_replay import (scene_selection,place_state,compare_interface,
                                             placement_options,recorded_interface)
from single0602_headless.frame_contract import resolve_profile
from single0602_headless.offline_job import verify_replay_identity
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.contracts import DEFAULT
from test_contract_and_input import metadata,state
from test_capture_plan import recorded

ROOT=Path(__file__).resolve().parents[1]


class SceneReplayTests(unittest.TestCase):
    def interface(self):
        return {'schema_version':1,'motion':{'joints':{'boom':{'axis':'Y','anchor':[1.,2.,3.]}}},
                'sensors':{'camera_front':{'fx':501.,'parent':'swing_link'}},
                'root_in_reference':metadata()['root_in_reference_row_matrix']}

    def fixture(self):
        meta=metadata();meta.update(recording_complete=True,scene='/missing/original.usda',scene_interface=self.interface())
        meta['asset_manifest']={'root_sha256':'old','used_layers':[{'path':'/missing/original.usda','sha256':'old'}]}
        scene=NS(project=ROOT,job={'replay':{'scene_policy':'environment'}},scene_interface=self.interface(),
                 source_states=[state(0)],motion=NS(controller=NS(states={'boom':NS(minimum=-10,maximum=10)})))
        return meta,scene

    def test_scene_edit_and_new_path_are_not_hash_whitelisted(self):
        profile=resolve_profile(ROOT,'/new/edited_scene.usda')
        self.assertEqual(profile['identity_policy'],'compatible_interface')
        self.assertEqual(profile['actual_scene'],'/new/edited_scene.usda')
        with self.assertRaises(ValueError):resolve_profile(ROOT,'/any.usda','unknown')

    def test_environment_independent_of_missing_source_and_rejects_interface_changes(self):
        meta,scene=self.fixture()
        self.assertTrue(verify_replay_identity(meta,scene)['verified'])
        for path,value in [('axis','Z'),('anchor',[1.,2.,4.])]:
            altered=deepcopy(scene.scene_interface);altered['motion']['joints']['boom'][path]=value
            scene.scene_interface=altered
            with self.assertRaisesRegex(ValueError,'interface.motion.joints.boom'):verify_replay_identity(meta,scene)
            scene.scene_interface=self.interface()
        scene.scene_interface['sensors']['camera_front']['fx']=502.
        with self.assertRaisesRegex(ValueError,'sensors.camera_front.fx'):verify_replay_identity(meta,scene)
        scene.scene_interface=self.interface();scene.source_states=[state(0,11)]
        with self.assertRaisesRegex(ValueError,'joint limit'):verify_replay_identity(meta,scene)

    def test_original_reproduction_still_checks_recorded_dependencies(self):
        meta,scene=self.fixture();scene.job['replay']['scene_policy']='original'
        scene.motion.frame_metadata=lambda:{k:meta[k] for k in ('asset_origin_version','swing_zero_mapping','root_in_reference_row_matrix')}
        scene.motion.config={'joints':meta['joint_definitions']}
        with self.assertRaises(FileNotFoundError):verify_replay_identity(meta,scene)

    def test_selection_policy_same_path_render_and_placement(self):
        meta={'scene':'/source.usda','render':{'background_dome':'/old/DomeLight'}}
        self.assertEqual(scene_selection({},meta)['target_scene'],'/source.usda')
        for target in ['/source.usda','/new.usda']:
            result=scene_selection({'scene_policy':'environment','target_scene':target,'placement_yaw_deg':'90'},meta)
            self.assertEqual(result['target_scene'],target);self.assertIsNone(result['render']['background_dome'])
            self.assertEqual(result['placement']['yaw_deg'],90.)
        for payload in [{'scene_policy':'other'},{'target_scene':'/new.usda'},
                        {'scene_policy':'environment'},{'placement_x_m':1}]:
            with self.assertRaises(ValueError):scene_selection(payload,meta)

    def test_rigid_placement_preserves_time_joints_mounts_and_source(self):
        source=state(.25,2);source['mounts']=[{'id':'sensor','position_m':[1,2,3]}];before=deepcopy(source)
        placed=place_state(source,{'translation_m':[10,20,3],'yaw_deg':90})
        for actual,expected in zip(placed['position_world_m'],[10,22,4]):self.assertAlmostEqual(actual,expected)
        for actual,expected in zip(placed['quaternion_xyzw'],[0,0,math.sqrt(.5),math.sqrt(.5)]):self.assertAlmostEqual(actual,expected)
        self.assertEqual(placed['joints_deg'],source['joints_deg']);self.assertEqual(placed['mounts'],source['mounts'])
        self.assertEqual(placed['t_sim_s'],source['t_sim_s']);self.assertEqual(source,before)
        for options in [{'translation_m':[1,2]},{'yaw_deg':float('nan')},{'yaw_deg':True}]:
            with self.assertRaises(ValueError):placement_options(options)

    def test_interface_numeric_tolerance_and_legacy_evidence(self):
        compare_interface({'x':[1.]},{'x':[1.+1e-8]})
        with self.assertRaises(ValueError):compare_interface({'x':1.},{'x':float('nan')})
        meta=metadata()
        with self.assertRaisesRegex(ValueError,'verified scene interface'):recorded_interface(meta,ROOT)
        known=json.loads((ROOT/'config/legacy_scene_interfaces.json').read_text())
        digest,item=next(iter(known.items()))
        legacy=metadata();legacy.update(asset_manifest={'root_sha256':digest,'used_layers':item['used_layers'],
            'asset_profile':{'asset_sha256':item['asset_sha256']}},root_in_reference_row_matrix=item['interface']['root_in_reference'],
            swing_zero_mapping=item['interface']['zero'])
        self.assertEqual(recorded_interface(legacy,ROOT),item['interface'])
        legacy['asset_manifest']['used_layers']=deepcopy(item['used_layers'])
        legacy['asset_manifest']['used_layers'][0]['sha256']='changed'
        with self.assertRaisesRegex(ValueError,'outside the verified'):recorded_interface(legacy,ROOT)

    def test_asgi_capture_plan_parity(self):
        try:from single0602_headless.web_asgi import build_app
        except ImportError:self.skipTest('Optional FastAPI is not installed')
        preview=Mock(return_value={'capture_plan':{'planned_groups':2}})
        app=build_app(NS(supervisor=NS(preview=preview)))
        endpoint=next(r.endpoint for r in app.routes if r.path=='/api/capture_plan')
        value=asyncio.run(endpoint(NS(query_params={'groups':'2','scene_policy':'environment','target_scene':'/new.usda'})))
        self.assertEqual(value['capture_plan']['planned_groups'],2)
        self.assertEqual(preview.call_args.args[0]['groups'],2)
        self.assertEqual(preview.call_args.args[0]['target_scene'],'/new.usda')

    @unittest.skipIf(os.name=='nt','Linux capture lease')
    def test_supervisor_snapshot_does_not_overwrite_target(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);source=recorded(out/'trajectories/source')
            meta=json.loads((source/'metadata.json').read_text());meta['scene_interface']=self.interface()
            (source/'metadata.json').write_text(json.dumps(meta));target=out/'target.usda';target.write_text('#usda 1.0\n')
            supervisor=CaptureSupervisor(ROOT,out,out/'absent.sock')
            child=Mock(pid=99999999);child.poll.return_value=None
            with patch('single0602_headless.capture_supervisor.subprocess.Popen',return_value=child):
                result=supervisor.start({'trajectory':str(source),'scene_policy':'environment','target_scene':str(target),'placement_x_m':3})
            job=json.loads((Path(result['directory'])/'job.json').read_text())
            self.assertEqual(job['scene'],str(target));self.assertIsNone(job['render']['background_dome'])
            self.assertEqual(job['replay']['placement']['translation_m'],[3.,0.,0.])
            self.assertEqual(json.loads((source/'metadata.json').read_text()),meta)


if __name__=='__main__':unittest.main()
