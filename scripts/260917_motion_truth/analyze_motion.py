"""Independent analytic ray-box truth from authored firing angles and GMO times."""
import json
from pathlib import Path
import numpy as np
root = Path(__file__).resolve().parent
ELEVATION = np.radians([-15., -10., -5., 0., 3., 5., 10., 15.])
def predictions(offset, ids, times, motion, speed, compensated, reference, reference_time, pattern='rotary', angular_speed=0.):
    # RTX rotary positive scan azimuth is clockwise in sensor XY; confirmed by
    # the independent static chamber control (tick 1 has negative y).
    angle = -offset.astype(float)*1e-9*10.*(2*np.pi)
    el = ELEVATION[ids] if pattern == 'rotary' else np.zeros(len(ids))
    if pattern == 'fixed':
        angle = np.zeros(len(ids))
    sensor_directions = np.column_stack([np.cos(el)*np.cos(angle), np.cos(el)*np.sin(angle), np.sin(el)])
    directions = sensor_directions.copy()
    yaw = np.radians(angular_speed)*times if motion == 'sensor' else np.zeros(len(times))
    directions[:, 0] = np.cos(yaw)*sensor_directions[:, 0] - np.sin(yaw)*sensor_directions[:, 1]
    directions[:, 1] = np.sin(yaw)*sensor_directions[:, 0] + np.cos(yaw)*sensor_directions[:, 1]
    sensor = np.zeros_like(directions)
    center = np.zeros_like(directions)
    if motion == 'sensor':
        sensor[:, 0] = speed*times
    elif motion == 'target':
        center[:, 0] = speed*times
    with np.errstate(divide='ignore', invalid='ignore'):
        distance_axis = (np.where(directions >= 0, 10., -10.) - (sensor-center))/directions
    distance_axis[np.abs(directions) < 1e-12] = np.inf
    distances = distance_axis.min(axis=1)
    xyz = distances[:, None]*sensor_directions
    if compensated:
        xyz = distances[:, None]*directions + sensor
        if reference == 'SENSOR' and motion == 'sensor':
            xyz[:, 0] -= speed*reference_time
            ref_yaw = np.radians(angular_speed)*reference_time
            x, y = xyz[:, 0].copy(), xyz[:, 1].copy()
            xyz[:, 0] = np.cos(ref_yaw)*x + np.sin(ref_yaw)*y
            xyz[:, 1] = -np.sin(ref_yaw)*x + np.cos(ref_yaw)*y
    return xyz
def stats(values):
    if not values or sum(len(v) for v in values) == 0:
        return {'n': 0}
    x = np.concatenate(values)
    return {'n': len(x), 'median_m': float(np.median(x)), 'p95_m': float(np.quantile(x, .95)),
            'max_m': float(x.max()), 'rmse_m': float(np.sqrt(np.mean(x*x)))}
def main():
    results = []
    for directory in sorted((root/'cases').iterdir()):
        analyze_case(directory, results)
    (root/'motion_analysis.json').write_text(json.dumps(results, indent=2))

def analyze_case(directory, results):
    path = directory/'result.json'
    if not path.exists():
        return
    record = json.loads(path.read_text())
    if 'motion' not in record.get('args', {}):
        return
    a = record['args']
    if record['status'] != 'collected':
        print(directory.name, record['status'], record.get('error', ''))
        return
    from deskew import PoseHistory
    histories = {}
    if a.get('driver', 'usd') == 'physics' and a['motion'] == 'sensor':
        for cycle in range(a['cycles']):
            updates = [u for u in record['updates'] if u['cycle'] == cycle]
            histories[cycle] = PoseHistory([round(u['physics_time']*1e9) for u in updates],
                [u['moving_position'] for u in updates],
                [u.get('moving_orientation_xyzw', [0,0,0,1]) for u in updates])
    errors, lagged, per_scan, flagged_errors, deskew_errors, surface_errors = [], [], [], [], [], []
    coverage = dict(output_records=0, flag_not_valid=0, flagged_near_zero=0, usable=0, nonfinite=0)
    for scan in record['samples']:
        # Warmup excluded from quantitative fit; raw data is retained for every scan.
        if scan['timestampNs'] < 300000000:
            continue
        data = np.load(directory/scan['file'])
        flagged = (data['flags'] & 64) != 0
        finite = np.isfinite(data['xyz']).all(axis=1)
        nearzero = np.linalg.norm(data['xyz'], axis=1) < .1
        valid = flagged & finite & ~nearzero
        coverage['output_records'] += len(flagged)
        coverage['flag_not_valid'] += int((~flagged).sum())
        coverage['flagged_near_zero'] += int((flagged & nearzero).sum())
        coverage['nonfinite'] += int((~finite).sum())
        coverage['usable'] += int(valid.sum())
        times = (scan['timestampNs']+data['timeOffsetNs'].astype(np.int64))*1e-9
        expected = predictions(data['timeOffsetNs'], data['emitterId'], times,
            a['motion'], a['speed'], a['compensated'], a['reference'], (scan['timestampNs']*1e-9), a.get('pattern', 'rotary'), a.get('angular_speed', 0.))
        flagged_errors.append(np.linalg.norm(data['xyz']-expected, axis=1)[flagged])
        delta = np.linalg.norm(data['xyz']-expected, axis=1)[valid]
        errors.append(delta)
        shifted = predictions(data['timeOffsetNs'], data['emitterId'], times-2/a['fps'],
            a['motion'], a['speed'], a['compensated'], a['reference'], (scan['timestampNs']*1e-9-2/a['fps']), a.get('pattern', 'rotary'), a.get('angular_speed', 0.))
        lagged.append(np.linalg.norm(data['xyz']-shifted, axis=1)[valid])
        if histories and not a['compensated'] and a['reference'] == 'SENSOR':
            corrected = histories[scan['cycle']].deskew(data['xyz'][valid],
                scan['timestampNs']+data['timeOffsetNs'][valid].astype(np.int64))
            # Independent static chamber surface check, valid even when the
            # actual trajectory differs from commanded constant angular speed.
            surface_errors.append(np.abs(np.abs(corrected)-10.).min(axis=1))
            world_truth = predictions(data['timeOffsetNs'], data['emitterId'], times,
                a['motion'], a['speed'], True, 'WORLD', 0., a.get('pattern', 'rotary'), a.get('angular_speed', 0.))
            deskew_errors.append(np.linalg.norm(corrected-world_truth[valid], axis=1))
        per_scan.append({'cycle': scan['cycle'], 'stamp': scan['timestampNs'],
                         'p95_m': float(np.quantile(delta, .95)), 'count': len(delta)})
    if a.get('accumulate', 1):
        coverage['expected_firings'] = len(per_scan)*(100 if a.get('pattern') == 'fixed' else 800)
        coverage['missing_output_records'] = coverage['expected_firings']-coverage['output_records']
    row = {'case': directory.name, 'args': a, 'scans': len(record['samples']),
           'nominal_trajectory_valid': not (a.get('angular_speed', 0.) and not a.get('zero_damping', False)),
           'stale_buffers_rejected': len(record['stale']), 'coverage_after_warmup': coverage,
           'returned_points_at_ray_time': stats(errors), 'all_flagged_points_at_ray_time': stats(flagged_errors),
           'world_deskew_from_recorded_physics_poses': stats(deskew_errors),
           'world_surface_residual_from_recorded_poses': stats(surface_errors),
           'diagnostic_minus_two_dt': stats(lagged), 'per_scan': per_scan}
    results.append(row)
    print(json.dumps({k:v for k,v in row.items() if k not in ['args','per_scan']}), flush=True)

if __name__ == '__main__':
    main()
