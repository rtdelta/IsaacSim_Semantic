"""Offline native-parser analysis, after capture. No fitted delays or poses."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import numpy as np


def wall_range(azimuth_deg, yaw_rad):
    # Native convention: azimuth increases toward -Y. Sensor origin is (0,0,0).
    angle = yaw_rad - np.deg2rad(azimuth_deg)
    directions = np.column_stack((np.cos(angle), np.sin(angle)))
    bounds = np.array([[-7., 10.], [-11., 8.]])
    planes = np.where(directions > 0, bounds[:, 1], bounds[:, 0])
    distances = np.full_like(directions, np.inf)
    np.divide(planes, directions, out=distances, where=np.abs(directions) > 1e-12)
    return np.min(distances, axis=1)


def p95(values):
    values = np.sort(np.asarray(values))
    return float(values[math.ceil(.95 * len(values)) - 1])


def analyze(out):
    from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
    def read(name):
        return json.loads((out / name).read_text())
    spec, plan, states, events = read('request.json'), read('plan.json'), read('physics.json'), read('events.json')
    actual = {s['step']: s for s in states}
    if len(actual) != len(states):
        raise ValueError('Duplicate actual physical-step record')
    active = [u for u in read('updates.json') if u['phase'] == 'motion_and_drain']
    if not active or any(u['after'] - u['before'] != 1 for u in active):
        raise ValueError('Not exactly one physics step per app update')
    for step in range(plan['motion_start'], plan['end']+1):
        s, prev = actual[step], actual[step-1]
        if abs(s['time_ns']-prev['time_ns']-1e9/60) > 2 or abs(s['dt']-1/60) > 2e-9:
            raise ValueError('Unexpected physical clock increment')
        expected = math.radians((step-plan['motion_start']+1)*spec['yaw_rate_deg_s']/60)
        if abs(s['yaw_rad']-expected) > 1e-8:
            raise ValueError('Actual input yaw does not match fixed PRE schedule')
    rows, per_ray, source_steps, identities, selected_steps = [], [], [], set(), []
    azimuths = np.asarray(read('effective_sensor.json')['omni:sensor:Core:emitterState:s001:azimuthDeg'])
    warmup = []
    for event in events:
        matches = [s for s in states if abs(s['time_ns']-event['source_ns']) <= 2
                   and abs(s['time_ns']-event['mapped_ns']) <= 2]
        if len(matches) != 1 or abs(event['source_ns']-event['mapped_ns']) > 2:
            raise ValueError('Source/reference time must uniquely identify the same physical step')
        state = matches[0]
        step = state['step']
        source_steps.append(step)
        raw = gzip.decompress((out / event['path']).read_bytes())
        if hashlib.sha256(raw).hexdigest() != event['sha256_uncompressed']:
            raise ValueError('Saved native payload hash mismatch')
        magic, major, minor, patch, size = struct.unpack_from('<IIIIQ', raw)
        if (magic, major, minor, patch) != (0x4e474d4f, 1, 0, 0) or not 264 <= size <= len(raw):
            raise ValueError('GMO version/size not qualified by this reproduction')
        if not np.array_equal(np.frombuffer(raw, '<f4', 16, 56).reshape(4, 4), np.eye(4)):
            raise ValueError('Nonidentity model-to-app transform is outside scope')
        owned = np.frombuffer(raw, np.uint8).copy()
        g = parse_generic_model_output_data(owned)
        identity = (int(g.frameId), int(g.timestampNs))
        if identity in identities:
            raise ValueError('Duplicate native frame/time identity')
        identities.add(identity)
        if (int(g.frameOfReference), int(g.elementsCoordsType), int(g.motionCompensationState)) != (0, 0, 0):
            raise ValueError('Expected SENSOR/CARTESIAN/NONCOMPENSATED')
        if int(g.scanComplete) != 1:
            raise ValueError('Incomplete native scan')
        valid = (np.asarray(g.flags) & 64) != 0
        ids = np.asarray(g.emitterId)[valid].astype(int)
        if sorted(ids.tolist()) != list(range(10)):
            raise ValueError('Expected exactly one valid return for each of all ten emitters')
        xyz = np.column_stack((g.x, g.y, g.z))[valid].astype(float)
        if not np.array_equal(xyz, np.asarray(event['extractor_xyz'])):
            raise ValueError('Native parser and point-cloud extractor disagree')
        if not np.isfinite(xyz).all():
            raise ValueError('Nonfinite native XYZ')
        distances = np.linalg.norm(xyz, axis=1)
        current = state['yaw_rad']
        previous = actual[step-1]['yaw_rad']
        predictions = {'current': wall_range(azimuths[ids], current),
                       'half': wall_range(azimuths[ids], (current+previous)/2),
                       'previous': wall_range(azimuths[ids], previous)}
        residuals = {name: p95(abs(value-distances)) for name, value in predictions.items()}
        if step < plan['motion_start']:
            warmup.append(residuals['current'])
        if step not in plan['targets']:
            continue
        selected_steps.append(step)
        header = {}
        for name in ('frameStart', 'frameEnd'):
            frame = getattr(g, name)
            x, y, z, w = frame.orientation
            header[name+'_yaw_deg'] = math.degrees(math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))
        row = {'target': len(rows)+1, 'source_step': step, 'frame_id': identity[0],
               'timestamp_ns': identity[1], 'yaw_deg': math.degrees(current),
               'valid_returns': len(ids), **header,
               **{name+'_p95_m': value for name, value in residuals.items()}}
        rows.append(row)
        for i, emitter in enumerate(ids):
            per_ray.append({'target': row['target'], 'emitter': int(emitter), 'observed_m': float(distances[i]),
                            **{name+'_predicted_m': float(values[i]) for name, values in predictions.items()}})
    if source_steps != sorted(set(source_steps)) or any(b-a != 6 for a, b in zip(source_steps, source_steps[1:])):
        raise ValueError('Native source cadence differs from exactly six physics steps')
    if selected_steps != plan['targets']:
        raise ValueError('Target coverage is incomplete; no sample may be dropped or substituted')
    if not warmup or max(warmup) > 1e-5:
        raise ValueError('Static nominal-ray check exceeds 10 micrometers')
    for name, data in (('samples.csv', rows), ('per_ray.csv', per_ray)):
        with (out / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    return {'measurement_qualified': True, 'targets': len(rows), 'native_events': len(events),
            'static_warmup_max_p95_m': max(warmup),
            'median_target_p95_m': {name: float(np.median([r[name+'_p95_m'] for r in rows]))
                                   for name in ('current', 'half', 'previous')},
            'targets_with_p95_le_10um': {name: sum(r[name+'_p95_m'] <= 1e-5 for r in rows)
                                        for name in ('current', 'half', 'previous')},
            'interpretation': 'Fixed geometric hypotheses only. SDK measurement-time semantics are unconfirmed.'}
