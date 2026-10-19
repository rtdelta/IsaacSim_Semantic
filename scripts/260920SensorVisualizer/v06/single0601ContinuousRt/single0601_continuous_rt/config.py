import json
import math
from fractions import Fraction
from pathlib import Path
from .common import ContractError


def integer(value, name, minimum=1):
    if type(value) is not int or not minimum <= value <= 9007199254740991:
        raise ContractError('invalid_config', name + ' must be an integer in the declared range')
    return value


def validate(job):
    if job.get('schema_version') != 4:
        raise ContractError('unknown_schema', 'Expected job schema 4')
    sections = ['scene', 'sensors', 'clock', 'capture', 'render', 'pipeline', 'output']
    if any(k not in job for k in sections):
        raise ContractError('invalid_config', 'Missing configuration section')
    if not isinstance(job['scene'], str) or not job['scene']:
        raise ContractError('invalid_config', 'Scene must be a nonempty asset path')
    for kind in ('camera_ids', 'lidar_ids'):
        ids = job['sensors'][kind]
        if ids is not None and (not isinstance(ids, list) or any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids))):
            raise ContractError('invalid_selection', 'Sensor IDs must be unique strings or null')
    if job['sensors']['camera_ids'] == [] and job['sensors']['lidar_ids'] == []:
        raise ContractError('empty_selection', 'Select at least one sensor')
    clock = job['clock']
    for name in ('physics_hz', 'loop_hz', 'sample_hz'):
        integer(clock[name], name)
    if clock['physics_hz'] != clock['loop_hz'] or clock['physics_hz'] % clock['sample_hz']:
        raise ContractError('invalid_frequency', 'loop=physics; physics/sample must be a positive integer')
    if clock['sample_hz'] not in (5, 10):
        raise ContractError('unsupported_frequency', 'First version supports common 10 Hz ticks and fixed 5 Hz extraction')
    cap = job['capture']
    if cap['backend'] not in ('auto_verified', 'continuous', 'barrier') or cap['policy'] not in ('strict_complete', 'strict_latest'):
        raise ContractError('invalid_config', 'Unknown backend or policy')
    for name in ('requested_groups', 'max_inflight_groups', 'state_history_max_records'):
        integer(cap[name], name)
    if cap['runtime_fallback'] is not False or cap['source_time_tolerance_ns'] != 2:
        raise ContractError('invalid_config', 'Runtime fallback is forbidden; source tolerance is exactly 2 ns')
    for name, upper in (('translation_tolerance_m', .001), ('rotation_tolerance_rad', .0001)):
        v = cap[name]
        if isinstance(v, bool) or not math.isfinite(v) or not 0 <= v <= upper:
            raise ContractError('invalid_config', 'Tolerance widening needs a separately versioned contract')
    if not math.isfinite(cap['group_timeout_wall_s']) or cap['group_timeout_wall_s'] <= 0:
        raise ContractError('invalid_config', 'Group deadline must be positive')
    render = job['render']
    if render.get('sensor_pose_mode','mounted') not in ('mounted','usd_rig'):
        raise ContractError('invalid_config','Unknown sensor render pose source')
    if render['mode'] != 'RealTimePathTracing' or render['formal_subframes'] != 1 or render['frame_generation'] is not False or render['motion_blur'] is not False:
        raise ContractError('invalid_config', 'RT2, one completion event, no frame generation or motion blur required')
    for name in ('dlss_mode', 'aa_mode', 'initial_warmup_min_updates', 'initial_warmup_max_updates'):
        integer(render[name], name, 0)
    if render['initial_warmup_max_updates'] < render['initial_warmup_min_updates']:
        raise ContractError('invalid_config', 'Invalid warmup bounds')
    pipe = job['pipeline']
    for name in ('max_buffer_bytes', 'slot_bytes', 'encoder_workers', 'encoded_queue_groups', 'segment_groups'):
        integer(pipe[name], name)
    if type(pipe['png_compress_level']) is not int or not 0 <= pipe['png_compress_level'] <= 9:
        raise ContractError('invalid_config', 'PNG compression level must be 0..9')
    if pipe['max_buffer_bytes'] < 6 * pipe['slot_bytes']:
        raise ContractError('buffer_budget', 'Budget must cover raw, encoded and arrival safety capacity')
    out = job['output']
    if out['require_readback_validation'] is not True or out['image_codec'] != 'png_lossless' or out['point_fields'] != ['x', 'y', 'z']:
        raise ContractError('invalid_config', 'Lossless PNG, XYZ and independent readback are required')
    return job


def load(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


class SamplingClock:
    def __init__(self, physics_hz, sample_hz, origin_ns=0, origin_step=0, first_target_step=None):
        if type(physics_hz) is not int or type(sample_hz) is not int or min(physics_hz, sample_hz) <= 0 or physics_hz % sample_hz:
            raise ContractError('invalid_frequency', 'Physics/sample must be an integer')
        self.physics_hz, self.sample_hz = physics_hz, sample_hz
        self.stride = physics_hz // sample_hz
        self.origin_ns, self.origin_step = origin_ns, origin_step
        self.first_target_step = first_target_step if first_target_step is not None else origin_step + self.stride
        if self.first_target_step <= origin_step:
            raise ContractError('invalid_epoch', 'First formal target must be after observed common tick')

    def time_ns(self, step):
        return self.origin_ns + round(Fraction((step - self.origin_step) * 1_000_000_000, self.physics_hz))

    def target(self, index):
        step = self.first_target_step + index * self.stride
        return step, self.time_ns(step)
