"""Reserved physics-domain IMU contract; not a formal frozen-capture driver."""
import importlib
import math


def _get(raw, name, default=None):
    return raw.get(name, default) if isinstance(raw, dict) else getattr(raw, name, default)


def _vector(raw, plural, legacy, components):
    value = _get(raw, plural, _get(raw, legacy))
    if value is not None:
        return [float(v) for v in value]
    return [float(_get(raw, modern, _get(raw, old))) for modern, old in components]


def normalize_reading(raw, sensor_id, frame_id, *, read_gravity):
    """Keep native time and measurements; report missing/invalid data explicitly."""
    result = {'sensor_id': sensor_id, 'frame_id': frame_id, 'is_valid': False,
              'status': 'invalid', 'read_gravity': bool(read_gravity),
              'source_model': 'native_physics_imu', 'orientation_xyzw': None,
              'sensor_time_s': None, 'physics_step': _get(raw, 'physics_step'),
              'linear_acceleration_m_s2': None, 'angular_velocity_rad_s': None,
              'covariance_source': 'unknown', 'sampling_domain': 'physics'}
    if raw is None or not bool(_get(raw, 'is_valid', True)):
        result['status'] = 'warming_or_invalid'
        return result
    try:
        result['sensor_time_s'] = float(_get(raw, 'time'))
        result['linear_acceleration_m_s2'] = _vector(raw, 'linear_acceleration', 'lin_acc',
            [('linear_acceleration_' + n, 'lin_acc_' + n) for n in 'xyz'])
        result['angular_velocity_rad_s'] = _vector(raw, 'angular_velocity', 'ang_vel',
            [('angular_velocity_' + n, 'ang_vel_' + n) for n in 'xyz'])
        q = _get(raw, 'orientation')
        if q is None and _get(raw, 'orientation_w') is not None:
            q = [_get(raw, 'orientation_' + n) for n in 'wxyz']
        if q is not None:
            q = [float(v) for v in q]
            if len(q) != 4 or abs(sum(v*v for v in q) - 1.) > 1e-3:
                raise ValueError('Invalid native orientation quaternion')
            result['orientation_xyzw'] = q[1:] + q[:1]
            result['native_quaternion_order'] = 'wxyz'
        a, w = result['linear_acceleration_m_s2'], result['angular_velocity_rad_s']
        values = [result['sensor_time_s'], *a, *w, *(result['orientation_xyzw'] or [])]
        if len(a) != 3 or len(w) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError('Non-finite or malformed native IMU sample')
        result.update(is_valid=True, status='valid')
    except (TypeError, ValueError, OverflowError) as exc:
        result['error'] = str(exc)
    return result


def ros_imu_fields(sample):
    """Pure mapping for ROS2 Imu; serialization stays in the ROS worker/probe."""
    if not sample.get('is_valid'):
        raise ValueError('Cannot export invalid native IMU data')
    q = sample.get('orientation_xyzw')
    return {'frame_id': sample['frame_id'], 'stamp_ns': round(sample['sensor_time_s'] * 1e9),
            'orientation': q, 'orientation_covariance': [0.] * 9 if q is not None else [-1.] + [0.] * 8,
            'linear_acceleration': sample['linear_acceleration_m_s2'],
            'angular_velocity': sample['angular_velocity_rad_s'],
            'linear_acceleration_covariance': [0.] * 9, 'angular_velocity_covariance': [0.] * 9}


class ImuProbeDriver:
    formal_capture_supported = False
    sampling_domain = 'physics'

    def __init__(self, prim_path, sensor_id, frame_id=None, read_gravity=True):
        self.prim_path, self.sensor_id = prim_path, sensor_id
        self.frame_id = frame_id or sensor_id
        self.read_gravity = bool(read_gravity)
        self.sensor = None
        self.last_time = None
        self.api = None

    def initialize(self):
        import omni.usd
        prim = omni.usd.get_context().get_stage().GetPrimAtPath(self.prim_path)
        if not prim or 'imu' not in (str(prim.GetTypeName()) + ' '.join(prim.GetAppliedSchemas())).lower():
            raise ValueError('Existing official IMU Prim required: ' + self.prim_path)
        try:
            module = importlib.import_module('isaacsim.sensors.experimental.physics')
            cls = module.IMUSensor
        except (ImportError, AttributeError):
            module = importlib.import_module('isaacsim.sensors.physics')
            cls = module.IMUSensor
        self.api = module.__name__
        self.sensor = cls(module.IMU(self.prim_path,reset_xform_op_properties=False)) if hasattr(module,'IMU') else cls(self.prim_path)
        self.last_time = None

    def read(self):
        if self.sensor is None:
            raise RuntimeError('IMU probe is not initialized, or was invalidated by Stop')
        if hasattr(self.sensor, 'get_sensor_reading'):
            raw = self.sensor.get_sensor_reading(read_gravity=self.read_gravity)
        elif hasattr(self.sensor, 'get_data'):
            raw = self.sensor.get_data(read_gravity=self.read_gravity)
        else:
            raw = self.sensor.get_current_frame(read_gravity=self.read_gravity)
        sample = normalize_reading(raw, self.sensor_id, self.frame_id, read_gravity=self.read_gravity)
        sample['api'] = self.api
        if sample['is_valid'] and sample['physics_step'] is None and hasattr(self.sensor,'get_data'):
            data=self.sensor.get_data(read_gravity=self.read_gravity)
            if data.get('time')==sample['sensor_time_s']:sample['physics_step']=data.get('physics_step')
        if sample['is_valid']:
            t = sample['sensor_time_s']
            if self.last_time is not None and t <= self.last_time:
                sample['status'] = 'repeated_physics_sample' if t == self.last_time else 'clock_reset_reinitialize_required'
            else:
                self.last_time = t
        return sample

    def close(self):
        self.sensor = None
        self.last_time = None
