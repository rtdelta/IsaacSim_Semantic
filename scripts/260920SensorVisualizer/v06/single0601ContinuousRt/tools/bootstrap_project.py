"""One-time source transplant and schema 4 config generation; no network."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = root.parent
package = root / 'single0601_continuous_rt'
(package / 'robot').mkdir(parents=True, exist_ok=True)
(root / 'config').mkdir(exist_ok=True)
provenance = []
names = ['__init__', 'articulation_motion', 'base_control', 'discovery', 'joint_control',
         'motion_profile', 'motion_update', 'performance', 'reference_frames', 'render_lease', 'robot_discovery']
for name in names + ['../geometry']:
    rel = Path('robot') / (name + '.py')
    source = old / 'sensor_visualizer_v06' / rel
    destination = package / rel
    data = source.read_text(encoding='utf-8').replace('sensor_visualizer_v06', 'single0601_continuous_rt').replace('/SensorVisualizerV06Frames', '/Single0601ContinuousRtFrames')
    if not destination.exists():
        with destination.open('w', encoding='utf-8', newline='\n') as output:
            output.write(data)
    provenance.append({'path': destination.resolve().relative_to(root).as_posix(),
                       'origin_path': source.resolve().as_posix(),
                       'origin_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                       'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'modified': data != source.read_text(encoding='utf-8')})
(root / 'docs/source_transplants.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
robot = json.loads((old / 'config/robot_sensors.json').read_text(encoding='utf-8'))
(root / 'config/robot_sensors.json').write_text(json.dumps(robot, indent=2), encoding='utf-8')
base = {'schema_version': 4,
 'scene': '/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda',
 'sensors': {'camera_ids': None, 'lidar_ids': None},
 'clock': {'physics_hz': 60, 'loop_hz': 60, 'sample_hz': 10},
 'capture': {'backend': 'auto_verified', 'policy': 'strict_complete', 'requested_groups': 300,
  'max_inflight_groups': 3, 'group_timeout_wall_s': 5.0, 'source_time_tolerance_ns': 2,
  'translation_tolerance_m': .001, 'rotation_tolerance_rad': .0001,
  'state_history_max_records': 1024, 'runtime_fallback': False},
 'render': {'mode': 'RealTimePathTracing', 'dlss_mode': 2, 'aa_mode': 3,
  'frame_generation': False, 'formal_subframes': 1, 'initial_warmup_min_updates': 8,
  'initial_warmup_max_updates': 120, 'motion_blur': False},
 'pipeline': {'max_buffer_bytes': 536870912, 'slot_bytes': 67108864, 'encoder_workers': 4,
  'encoded_queue_groups': 2, 'png_compress_level': 1, 'segment_groups': 1000},
 'output': {'directory': '/root/gpufree-data/semantic/output/single0601ContinuousRt',
  'require_readback_validation': True, 'image_codec': 'png_lossless', 'point_fields': ['x', 'y', 'z']}}
variants = {'strict_scene18': (None, None), 'single_camera': (['front'], []),
            'single_lidar': ([], ['MyAiry_front']), 'mixed_pair': (['front'], ['MyAiry_front']),
            'benchmark_scene18': (None, None)}
for name, (cameras, lidars) in variants.items():
    job = json.loads(json.dumps(base))
    job['sensors'] = {'camera_ids': cameras, 'lidar_ids': lidars}
    if name == 'benchmark_scene18':
        job['capture']['requested_groups'] = 220
    path = root / 'config' / (name + '.json')
    if not path.exists():
        path.write_text(json.dumps(job, indent=2), encoding='utf-8')
print(json.dumps({'transplanted_files': len(provenance), 'configurations': list(variants)}))
