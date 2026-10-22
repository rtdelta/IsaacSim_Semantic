from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from single0602_headless.contracts import load_job
from single0602_headless.launch_config import resolve_interactive_job, snapshot_launch
from single0602_headless.sensor_catalog import candidate_from_record, assign_ids, select_candidates, camera_calibration
from single0602_headless.scene_replay import comparable_interfaces, scene_selection
from single0602_headless.imu_interface import normalize_reading, ros_imu_fields, ImuProbeDriver

ROOT = Path(__file__).resolve().parents[1]


def record(path, typ='Camera', attributes=None, category='world_static'):
    return {'path': path, 'type_name': typ, 'attributes': attributes or {},
            'binding': {'category': category, 'body_path': None}}


class LaunchTests(unittest.TestCase):
    def test_scene_override_does_not_inherit_old_dome(self):
        job, info = resolve_interactive_job(ROOT, scene='/new site/new.usda', check_files=False)
        self.assertEqual(job['scene'], '/new site/new.usda')
        self.assertIsNone(job['render']['background_dome'])
        self.assertEqual(info['configuration_sources']['scene'], 'cli')
        old, _ = resolve_interactive_job(ROOT, check_files=False)
        self.assertEqual(old['render']['background_dome'], '/environment_Fangshan_02/DomeLight')

    def test_explicit_job_wins_over_absent_cli_and_cli_wins_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'job.json'
            p.write_text(json.dumps({'scene': '/job.usda', 'output_directory': 'job-output',
                                    'render': {'background_dome': '/Lights/Dome'}}))
            job, _ = resolve_interactive_job(ROOT, job_path=p, scene='/cli.usda', check_files=False)
            self.assertEqual(job['output_directory'], 'job-output')
            self.assertEqual(job['render']['background_dome'], '/Lights/Dome')
            job, _ = resolve_interactive_job(ROOT, job_path=p, scene='/cli.usda',
                                             background_dome='', output=d, check_files=False)
            self.assertIsNone(job['render']['background_dome'])
            self.assertEqual(job['output_directory'], str(Path(d).resolve()))

    def test_snapshots_are_distinct_and_input_is_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            job, info = resolve_interactive_job(ROOT, output=d, check_files=False)
            before = deepcopy(job)
            first, a = snapshot_launch(job, info)
            second, b = snapshot_launch(job, info)
            self.assertNotEqual(first, second)
            self.assertEqual(job, before)
            self.assertEqual(json.loads(first.read_text())['launch'], a['launch'])
            self.assertTrue((first.parent / 'launch.json').is_file())

    def test_invalid_inputs_rejected(self):
        for scene in ('relative.usda', '/scene.zip', '/missing/scene.usda'):
            with self.assertRaises(ValueError): resolve_interactive_job(ROOT, scene=scene)
        for resolution in ([0, 10], [True, 10], [10], [10, 999999]):
            with self.assertRaises(ValueError): load_job(overrides={'sensors': {'camera_resolution': resolution}})


class CatalogTests(unittest.TestCase):
    def candidates(self, records):
        rows = [candidate_from_record(r) for r in records]
        return assign_ids([r for r in rows if r], '/Site/Machine')

    def test_world_and_robot_arbitrary_names_single_types_and_zero(self):
        rows = self.candidates([record('/Site/Tripod/Anything'),
            record('/Site/Machine/boom_link/Another', category='robot_body')])
        registry = select_candidates(rows, {})
        self.assertEqual(len(registry['cameras']), 2)
        self.assertEqual(registry['lidars'], [])
        self.assertEqual({r['binding']['category'] for r in registry['cameras']}, {'world_static', 'robot_body'})
        self.assertEqual(select_candidates([], {}), {'cameras': [], 'lidars': [], 'imus': []})
        rows = self.candidates([record('/Site/Range', 'OmniLidar', {'omni:sensor:Core:instantLidar': True})])
        self.assertEqual(len(select_candidates(rows, {})['lidars']), 1)

    def test_duplicate_names_and_root_namespace_change_are_stable(self):
        paths = ['/Site/Machine/boom_link/Camera', '/Site/Machine/arm_link/Camera', '/Site/Tripod/Camera']
        first = self.candidates([record(p) for p in paths])
        second = self.candidates([record(p) for p in reversed(paths)])
        self.assertEqual({r['prim_path']: r['id'] for r in first}, {r['prim_path']: r['id'] for r in second})
        self.assertEqual(len({r['frame_id'] for r in first}), 3)
        third = [candidate_from_record(record(p.replace('/Site/Machine', '/Other/Excavator'))) for p in paths[:2]]
        assign_ids(third, '/Other/Excavator')
        self.assertEqual([r['id'] for r in first[:2]], [r['id'] for r in third])

    def test_specialized_invalid_lens_never_falls_back_to_pinhole(self):
        rows = self.candidates([record('/Wrong', attributes={'omni:lensdistortion:model': 'opencvFisheye'}),
                                record('/Rolling', 'OmniLidar'), record('/Imu', 'IsaacImuSensor')])
        self.assertFalse(any(r['capturable'] for r in rows))
        self.assertEqual(select_candidates(rows, {})['cameras'], [])
        for row in rows:
            with self.assertRaises(ValueError): select_candidates(rows, {row['kind'][:-1] + '_ids': [row['id']]})
        self.assertFalse(rows[2]['formal_capture_supported'])

    def test_pinhole_calibration_matches_output_aspect(self):
        cal = camera_calibration({'focalLength': 20., 'horizontalAperture': 40., 'verticalAperture': 40.}, [640, 480])
        self.assertEqual(cal['model'], 'pinhole')
        self.assertEqual(cal['intrinsics'], {'fx': 320., 'fy': 320., 'cx': 320., 'cy': 240.})
        self.assertEqual(cal['vertical_aperture'], 30.)

    def test_native_pinhole_and_film_offsets_keep_the_actual_model(self):
        prefix='omni:lensdistortion:opencvPinhole:'
        attrs={'omni:lensdistortion:model':'opencvPinhole',prefix+'imageSize':[640,480],
               prefix+'fx':500,prefix+'fy':501,prefix+'cx':319,prefix+'cy':239,prefix+'k4':.01}
        cal=camera_calibration(attrs)
        self.assertEqual(cal['distortion_model'],'rational_polynomial')
        self.assertEqual(len(cal['distortion']),8)
        self.assertEqual(cal['intrinsics']['fx'],500)
        cal=camera_calibration({'horizontalAperture':40,'horizontalApertureOffset':2,'verticalApertureOffset':1},[640,480])
        self.assertEqual(cal['intrinsics']['cx'],288)
        self.assertEqual(cal['intrinsics']['cy'],256)

    def test_explicit_empty_and_recorded_selection_are_not_auto(self):
        rows = self.candidates([record('/One'), record('/Two')])
        self.assertEqual(select_candidates(rows, {'camera_ids': []})['cameras'], [])
        saved = {'cameras': [deepcopy(rows[0])]}
        self.assertEqual(len(select_candidates(rows, {}, saved)['cameras']), 1)
        with self.assertRaises(ValueError): select_candidates(rows, {'camera_ids': ['missing']})

    def test_known_saved_ids_survive_new_candidates(self):
        rows = [candidate_from_record(record('/Renamed/Camera'))]
        assign_ids(rows, '/Robot', recorded={'cameras': [{'id': 'front', 'prim_path': '/Renamed/Camera'}]})
        self.assertEqual(rows[0]['id'], 'front')

    def test_environment_names_do_not_steal_existing_robot_camera_ids(self):
        onboard='/Robot/swing_link/Camera'
        rows=[candidate_from_record(record('/Tripod/front')),candidate_from_record(record(onboard))]
        assign_ids(rows,'/Robot',{onboard:'front'})
        self.assertEqual(next(r['id'] for r in rows if r['prim_path']==onboard),'front')
        self.assertNotEqual(rows[0]['id'],'front')

    def test_unrecorded_dynamic_carrier_is_reported(self):
        row = candidate_from_record(record('/OtherRobot/Camera', category='unsupported_dynamic'))
        self.assertFalse(row['capturable'])
        self.assertIn('unrecorded', row['issues'][0])

    def test_lidar_names_cannot_collide_with_camera_generated_frames(self):
        camera='/Site/Machine/swing_link/Camera'
        records=[record(camera),record('/A/camera_front','OmniLidar',{'omni:sensor:Core:instantLidar':True}),
                 record('/A/camera_front_optical','OmniLidar',{'omni:sensor:Core:instantLidar':True})]
        first=[candidate_from_record(r) for r in records]
        second=[candidate_from_record(r) for r in reversed(records)]
        for rows in (first,second):
            assign_ids(rows,'/Site/Machine',{camera:'front'})
            self.assertEqual(next(r['id'] for r in rows if r['prim_path']==camera),'front')
            token_sets=[{r['id'],r['mount_id'],r['frame_id']} for r in rows]
            self.assertTrue(all(not a&b for i,a in enumerate(token_sets) for b in token_sets[i+1:]))
        self.assertEqual({r['prim_path']:r['id'] for r in first},{r['prim_path']:r['id'] for r in second})


class SensorPolicyTests(unittest.TestCase):
    def test_legacy_fisheye_accepts_only_new_provenance_field(self):
        old={'schema_version':1,'sensors':{'camera_front':{'configuration':{'model':'opencv_fisheye','fx':10}}}}
        new=deepcopy(old);new['schema_version']=2
        new['sensors']['camera_front'].update(category='robot_body')
        new['sensors']['camera_front']['configuration']['resolution_source']='USD_opencvFisheye_imageSize'
        self.assertEqual(*comparable_interfaces(old,new))
        new['sensors']['camera_front']['configuration']['fx']=11
        a,b=comparable_interfaces(old,new)
        self.assertNotEqual(a,b)
    def test_target_sensors_decouple_only_sensor_configuration(self):
        old = {'schema_version': 1, 'motion': {'axis': 'Y'}, 'sensors': {'old': 1}}
        new = {'schema_version': 2, 'motion': {'axis': 'Y'}, 'sensors': {'new': 2}}
        a, b = comparable_interfaces(old, new, 'target_scene')
        self.assertEqual(a, b)
        self.assertIn('sensors', old)
        with self.assertRaises(ValueError): scene_selection({'sensor_policy': 'target_scene'}, {'scene': '/a.usda'})
        self.assertEqual(scene_selection({'scene_policy': 'environment', 'target_scene': '/b.usda',
                                          'sensor_policy': 'target_scene'}, {'scene': '/a.usda'})['sensor_policy'], 'target_scene')


class ImuInterfaceTests(unittest.TestCase):
    def test_native_struct_and_mapping_keep_time_axes_gravity(self):
        raw = NS(is_valid=True, time=2.5, linear_acceleration_x=0., linear_acceleration_y=0.,
                 linear_acceleration_z=9.81, angular_velocity_x=1., angular_velocity_y=2., angular_velocity_z=3.,
                 orientation_w=1., orientation_x=0., orientation_y=0., orientation_z=0.)
        sample = normalize_reading(raw, 'imu', 'imu_frame', read_gravity=True)
        self.assertTrue(sample['is_valid'])
        self.assertEqual(sample['orientation_xyzw'], [0, 0, 0, 1])
        self.assertEqual(ros_imu_fields(sample)['stamp_ns'], 2500000000)
        self.assertEqual(sample['linear_acceleration_m_s2'], [0., 0., 9.81])
        self.assertTrue(sample['read_gravity'])
        self.assertFalse(ImuProbeDriver.formal_capture_supported)

    def test_invalid_and_missing_fields_are_not_fabricated(self):
        self.assertFalse(normalize_reading(None, 'imu', 'imu', read_gravity=False)['is_valid'])
        value = normalize_reading({'time': 1., 'linear_acceleration': [0, 0, 0], 'angular_velocity': [0, 0, 0]}, 'imu', 'imu', read_gravity=False)
        self.assertTrue(value['is_valid'])
        self.assertIsNone(value['orientation_xyzw'])
        self.assertEqual(ros_imu_fields(value)['orientation_covariance'][0], -1)
        value['is_valid'] = False
        with self.assertRaises(ValueError): ros_imu_fields(value)


if __name__ == '__main__': unittest.main()
