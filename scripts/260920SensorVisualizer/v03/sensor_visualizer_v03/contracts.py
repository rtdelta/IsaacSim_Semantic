"""Portable validated task specification and exact sample clock."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import json
import math

DEFAULT = {
    'schema_version': 3,
    'scene': '/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda',
    'mode': 'offline', 'sample_hz': 10, 'groups': 100, 'physics_hz': 60,
    'output_directory': '/root/gpufree-data/semantic/output/sensor_visualizer/v03',
    'max_real_time_factor': 0.1,
    'sensors': {'lidar_ids': None, 'camera_ids': None},
    'render': {'mode': 'RealTimePathTracing', 'dlss_mode': 2, 'aa_mode': 3,
               'warmup_subframes': 4, 'camera_subframes': 16, 'capture_subframes': 2},
    'pipeline': {'slots': 3, 'slot_bytes': 67108864, 'encoder_workers': 4,
                 'png_compress_level': 1, 'segment_groups': 100, 'timeout_s': 120},
    'preview': {'enabled': False, 'wall_hz': 5, 'ros_domain_id': 0},
    'motion': {'joints': {}, 'tilt': {}, 'base': {}},
    'mount_poses': {}, 'events': [],
    'capture': {'ready_timeout_s':30, 'max_retries':3, 'max_progress_updates':8},
    'diagnostics': {'level':'basic', 'resource_period_ms':1000, 'detail_group_range':None,
                    'event_queue_capacity':8192, 'flush_interval_ms':250, 'ring_history_seconds':10,
                    'slow_stage_ms':500, 'export_trace_on_stop':False, 'native_profiler':'off'}
}


def merge(base, change):
    result = deepcopy(base)
    for key, value in change.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def load_job(path=None, overrides=None):
    raw = json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
    job = merge(merge(DEFAULT, raw), overrides or {})
    if job['schema_version'] != 3 or job['mode'] not in ('offline', 'interactive'):
        raise ValueError('Expected schema_version=3 and mode offline/interactive')
    hz = Fraction(str(job['sample_hz']))
    physics = Fraction(str(job['physics_hz']))
    if not 0 < hz <= physics or (physics/hz).denominator != 1:
        raise ValueError('sample_hz must divide physics_hz and be positive')
    if type(job['groups']) is not int or job['groups'] < 1:
        raise ValueError('groups must be a positive integer')
    if not isinstance(job['scene'], str) or not job['scene'].startswith('/'):
        raise ValueError('scene must be an absolute Linux asset path')
    if not 0 < float(job['max_real_time_factor']) <= 0.1:
        raise ValueError('Interactive max_real_time_factor must be in (0, 0.1]')
    p = job['pipeline']
    for key in ('slots', 'slot_bytes', 'encoder_workers', 'segment_groups'):
        if type(p[key]) is not int or p[key] < 1: raise ValueError('Invalid pipeline '+key)
    if not 0 <= p['png_compress_level'] <= 9 or not 0 < float(p['timeout_s']) <= 3600:
        raise ValueError('Invalid PNG compression or timeout')
    for name in ('warmup_subframes', 'capture_subframes', 'camera_subframes'):
        if type(job['render'][name]) is not int or job['render'][name] < 1:
            raise ValueError('Invalid render '+name)
    if job['render']['mode'] not in ('RealTimePathTracing', 'PathTracing'):
        raise ValueError('Unsupported render mode')
    if job['render']['dlss_mode'] not in (0,1,2,3) or job['preview']['wall_hz']<=0:
        raise ValueError('Invalid DLSS mode or preview rate')
    for event in job['events']:
        if type(event.get('group')) is not int or not 0 <= event['group'] < job['groups']:
            raise ValueError('Event group outside task')
    d=job['diagnostics']; c=job['capture']
    if d['level'] not in ('basic','diagnostic','deep') or d['native_profiler'] not in ('off','markers'):
        raise ValueError('Invalid diagnostics level or profiler mode')
    for name in ('resource_period_ms','event_queue_capacity','flush_interval_ms','ring_history_seconds','slow_stage_ms'):
        if type(d[name]) is not int or d[name]<1: raise ValueError('Invalid diagnostics '+name)
    if d['resource_period_ms']<100 or d['event_queue_capacity']<32:
        raise ValueError('Resource period >=100 ms and queue >=32 required')
    selected=d['detail_group_range']
    if selected is not None and (not isinstance(selected,list) or len(selected)!=2 or any(type(n) is not int or n<0 for n in selected) or selected[0]>selected[1]):
        raise ValueError('detail_group_range must be [first,last] or null')
    if not 0<float(c['ready_timeout_s'])<=300: raise ValueError('Invalid ready timeout')
    for name in ('max_retries','max_progress_updates'):
        if type(c[name]) is not int or not 0<=c[name]<=100: raise ValueError('Invalid capture '+name)
    # Reject NaN/Infinity throughout controls before passing them to native code.
    json.dumps(job, allow_nan=False)
    return job


class SampleClock:
    def __init__(self, hz, epoch_ns=0):
        self.rate = Fraction(str(hz))
        if self.rate <= 0: raise ValueError('Invalid clock rate')
        self.epoch_ns = int(epoch_ns)

    def stamp(self, group):
        if type(group) is not int or group < 0: raise ValueError('Invalid group')
        value = Fraction(group * 1_000_000_000, 1)/self.rate
        # Round once from the frame number, never accumulate floating dt.
        return self.epoch_ns + (value.numerator*2//value.denominator + 1)//2


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(path)


def assert_frozen(before, after, tolerance=1e-9):
    if not math.isfinite(before) or not math.isfinite(after) or abs(before-after) > tolerance:
        raise RuntimeError(f'Simulation time advanced during capture: {before} -> {after}')
