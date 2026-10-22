"""Select one verified native message per sensor/group using official rosbag2.

The source bag remains untouched. CDR payloads, header stamps and recorded
timestamps are copied byte for byte. Two passes bound memory to one message.
"""
import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def stamp_ns(stamp):
    return stamp.sec * 10**9 + stamp.nanosec


def reader_for(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    return reader


def payload_hash(message, kind):
    if kind == 'camera':
        if message.encoding not in ('rgb8', 'rgba8'):
            raise ValueError('Unsupported image encoding ' + message.encoding)
        channels = 3 if message.encoding == 'rgb8' else 4
        value = np.ndarray((message.height, message.width, channels), dtype='u1',
                           buffer=message.data, strides=(message.step, channels, 1))[:, :, :3]
    else:
        fields = {field.name: field for field in message.fields}
        value = np.empty((message.height, message.width, 3), dtype='<f4')
        for index, name in enumerate(('x', 'y', 'z')):
            if fields[name].datatype != 7:
                raise ValueError('XYZ must be FLOAT32')
            value[:, :, index] = np.ndarray(
                (message.height, message.width), dtype='>f4' if message.is_bigendian else '<f4',
                buffer=message.data, offset=fields[name].offset,
                strides=(message.row_step, message.point_step))
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def transform_matches(actual, expected):
    t = actual.transform.translation
    q = actual.transform.rotation
    return (actual.header.frame_id == expected['parent'] and
            max(abs(a-b) for a, b in zip((t.x, t.y, t.z), expected['translation'])) <= 2e-3 and
            abs(np.dot((q.x, q.y, q.z, q.w), expected['quaternion_xyzw'])) >= 1-2e-5)


def export(source, destination):
    source, destination = Path(source), Path(destination)
    verified = json.loads((source/'group_validation.json').read_text())
    assert verified['ok'], 'Source group validation must succeed before export'
    groups = [json.loads(line) for line in (source/'groups.jsonl').read_text().splitlines()]
    spec = json.loads((source/'spec.json').read_text())
    assert len(groups) == spec['measure_frames']
    sensors = json.loads((source/'sensor_manifest.json').read_text())['sensors']
    sensor_topics = {s['topic']: s for s in sensors}
    required_topics = set(sensor_topics) | {s['info_topic'] for s in sensors if s['kind'] == 'camera'} | {'/joint_states', '/clock'}
    by_stamp = {}
    for group in groups:
        for offset in range(-2, 3):
            key = round(group['native_time_s']*1e9) + offset
            assert key not in by_stamp, 'Overlapping group times'
            by_stamp[key] = group

    reader = reader_for(source/'bag')
    metadata = reader.get_all_topics_and_types()
    types = {t.name: get_message(t.type) for t in metadata}
    selected = {}
    ordinal = 0
    while reader.has_next():
        topic, raw, recorded_ns = reader.read_next()
        msg = deserialize_message(raw, types[topic])
        if topic == '/tf':
            stamps = {stamp_ns(t.header.stamp) for t in msg.transforms}
            if len(stamps) != 1:
                ordinal += 1
                continue
            native_stamp = next(iter(stamps))
        elif topic == '/clock':
            native_stamp = stamp_ns(msg.clock)
        else:
            native_stamp = stamp_ns(msg.header.stamp)
        group = by_stamp.get(native_stamp)
        if group is None:
            ordinal += 1
            continue
        key = (group['group'], topic, '')
        good = True
        if topic in sensor_topics:
            kind = sensor_topics[topic]['kind']
            wanted = group['images'][topic]['sha256'] if kind == 'camera' else group['lidars'][topic]['sha256_xyz']
            good = payload_hash(msg, kind) == wanted
        elif topic == '/tf':
            children = tuple(sorted(t.child_frame_id for t in msg.transforms))
            good = bool(children) and all(
                t.child_frame_id in group['expected_tf'] and
                transform_matches(t, group['expected_tf'][t.child_frame_id]) for t in msg.transforms)
            key = (group['group'], topic, '|'.join(children))
        elif topic == '/joint_states':
            joints = dict(zip(msg.name, msg.position))
            good = all(abs(joints.get(n, float('inf'))-v) <= 1e-3 for n, v in group['joints_rad'].items())
        if good:
            selected[key] = {'source_ordinal': ordinal, 'group': group['group'], 'topic': topic,
                             'header_stamp_ns': native_stamp, 'recorded_ns': recorded_ns,
                             'cdr_sha256': hashlib.sha256(raw).hexdigest(), 'children': list(children) if topic == '/tf' else []}
        ordinal += 1
    del reader
    for group in groups:
        rows = [r for r in selected.values() if r['group'] == group['group']]
        assert required_topics <= {r['topic'] for r in rows}, 'Missing selected topic in group ' + str(group['group'])
        children = [child for r in rows for child in r['children']]
        assert set(children) == set(group['expected_tf']), 'Incomplete TF group'
        assert len(children) == len(set(children)), 'Overlapping TF message sets'

    destination.mkdir(parents=True, exist_ok=False)
    for filename in ('spec.json', 'sensor_manifest.json', 'groups.jsonl', 'engine_result.json',
                     'expected_final_transforms.json', 'input_trajectory.jsonl', 'source_manifest.json'):
        shutil.copyfile(source/filename, destination/filename)
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(destination/'bag'), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    used_topics = {r['topic'] for r in selected.values()}
    for topic in metadata:
        if topic.name in used_topics:
            writer.create_topic(topic)
    index = {r['source_ordinal']: r for r in selected.values()}
    counts = collections.Counter()
    reader = reader_for(source/'bag')
    ordinal = 0
    while reader.has_next():
        topic, raw, recorded_ns = reader.read_next()
        if ordinal in index:
            row = index[ordinal]
            assert row['cdr_sha256'] == hashlib.sha256(raw).hexdigest()
            assert row['recorded_ns'] == recorded_ns and row['topic'] == topic
            writer.write(topic, raw, recorded_ns)
            counts[topic] += 1
        ordinal += 1
    del reader, writer
    assert sum(counts.values()) == len(index)
    manifest = {'source_capture': str(source), 'groups': len(groups), 'messages': sum(counts.values()),
                'counts': dict(counts), 'selection': sorted(selected.values(), key=lambda r: r['source_ordinal']),
                'policy': 'Last verified matching native payload per sensor/group; native CDR and both timestamps unchanged; source bag retained.'}
    (destination/'selection_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'groups': len(groups), 'messages': manifest['messages'], 'destination': str(destination)}))


if __name__ == '__main__':
    export(sys.argv[1], sys.argv[2])
