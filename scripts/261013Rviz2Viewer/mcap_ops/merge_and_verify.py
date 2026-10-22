"""Merge the confirmed remote capture with installed ROS 2, then verify bytes."""
import collections
import datetime
import hashlib
import itertools
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from verify_mcap_records import messages, file_digest, update_ros_digest

SOURCE = Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300/capture/captures/20261013_142524_685978_f13b03ee/bag_unified')
DESTINATION = SOURCE.parent / 'bag_merged'
NAMES = ['bag_unified_0.mcap', 'bag_unified_1.mcap', 'bag_unified_2.mcap', 'metadata.yaml']
EXPECTED_HASHES = [
    'f4ded7027fbfc2ea441c203ad7123b62ce30bbe3bd15f41ce1134af150390188',
    '05014ed970e60d5af74169750a9490d64bd4cda11cad9b7cda14540430ccf6da',
    '95562bd85222d97b9354cb54e5c264badfea6ce908006361024d42023782cab4',
    '57ee17ff5160ba58d0c3b18ed7fcc63601703fd8c9964214d49527ce1257d6a6',
]


def main():
    import rosbag2_py
    import yaml

    started = time.monotonic()
    assert SOURCE.resolve() == SOURCE and not SOURCE.is_symlink()
    resume = '--verify-existing' in sys.argv
    assert DESTINATION.is_dir() if resume else not DESTINATION.exists(), 'Unexpected destination state'
    assert shutil.disk_usage(SOURCE).free > 6 * 1024 ** 3
    before = []
    for name, expected in zip(NAMES, EXPECTED_HASHES):
        path = SOURCE / name
        assert path.is_file() and not path.is_symlink()
        st = path.stat()
        observed = file_digest(path)
        assert observed == expected, 'Source changed since the verified download: ' + name
        before.append({'name': name, 'bytes': st.st_size, 'mtime_ns': st.st_mtime_ns, 'sha256': observed})
    control = SOURCE.parent / 'merge_control_20261013'
    if not resume:
        control.mkdir(exist_ok=False)
        options = control / 'output_options.yaml'
        options.write_text(yaml.safe_dump({'output_bags': [{
            'uri': str(DESTINATION), 'storage_id': 'mcap',
            'all_topics': True, 'include_hidden_topics': True,
            'max_bagfile_size': 0, 'max_bagfile_duration': 0,
            'max_cache_size': 0,
        }]}))
        print(json.dumps({'phase': 'convert_started', 'source': str(SOURCE), 'destination': str(DESTINATION)}), flush=True)
        with (control / 'convert.log').open('w') as log:
            subprocess.run(['/opt/ros/jazzy/bin/ros2', 'bag', 'convert', '--input', str(SOURCE), 'mcap', '--output-options', str(options)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240)
    else:
        assert control.is_dir()
    outputs = list(DESTINATION.glob('*.mcap'))
    assert len(outputs) == 1
    output = outputs[0]
    print(json.dumps({'phase': 'convert_finished', 'bytes': output.stat().st_size}), flush=True)
    source_messages = itertools.chain.from_iterable(messages(SOURCE / name) for name in NAMES[:3])
    output_messages = messages(output)
    counts = collections.Counter()
    stamps, first, last = set(), None, None
    native_digest = hashlib.sha256()
    ros_digest = hashlib.sha256()
    total = 0
    for old, new in itertools.zip_longest(source_messages, output_messages):
        assert old is not None and new is not None, 'Message count changed'
        assert old == new, 'Schema/channel, sequence, timestamps or serialized payload changed at message ' + str(total)
        channel, sequence, log_time, publish_time, payload = new
        topic = channel[0]
        counts[topic] += 1
        update_ros_digest(ros_digest, topic, log_time, payload)
        native_digest.update(bytes.fromhex(file_digest_bytes(payload)))
        native_digest.update(json.dumps([topic, sequence, log_time, publish_time], separators=(',', ':')).encode())
        if topic == '/sensor_visualizer/frame_index':
            stamps.add(log_time)
        first = log_time if first is None else min(first, log_time)
        last = log_time if last is None else max(last, log_time)
        total += 1
    assert total == 9006 and len(counts) == 32 and len(stamps) == 300
    ordered_stamps = sorted(stamps)
    assert all(b - a == 100_000_000 for a, b in zip(ordered_stamps, ordered_stamps[1:]))
    metadata_path = DESTINATION / 'metadata.yaml'
    metadata_document = yaml.safe_load(metadata_path.read_text())
    metadata = metadata_document['rosbag2_bagfile_information']
    assert metadata['relative_file_paths'] == [output.name]
    assert metadata['message_count'] == total
    assert {x['topic_metadata']['name']: x['message_count'] for x in metadata['topics_with_message_count']} == dict(counts)
    metadata_correction = None
    if metadata['files'][0]['message_count'] != total:
        original = control / 'metadata.generated.yaml'
        assert not original.exists()
        shutil.copy2(metadata_path, original)
        metadata_correction = {'field': 'files[0].message_count', 'generated': metadata['files'][0]['message_count'], 'actual': total, 'original_metadata': str(original)}
        metadata['files'][0]['message_count'] = total
        metadata_path.write_text(yaml.safe_dump(metadata_document, sort_keys=False))
    assert yaml.safe_load(metadata_path.read_text())['rosbag2_bagfile_information']['files'][0]['message_count'] == total
    ros_results = []
    for uri in [DESTINATION, output]:
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(uri), storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
        digest, n = hashlib.sha256(), 0
        while reader.has_next():
            topic, payload, stamp = reader.read_next()
            update_ros_digest(digest, topic, stamp, payload)
            n += 1
        reader.close()
        assert n == total and digest.hexdigest() == ros_digest.hexdigest()
        ros_results.append({'uri': str(uri), 'messages': n, 'ordered_content_sha256': digest.hexdigest()})
    for item in before:
        st = (SOURCE / item['name']).stat()
        assert (st.st_size, st.st_mtime_ns) == (item['bytes'], item['mtime_ns'])
        assert file_digest(SOURCE / item['name']) == item['sha256']
    manifest = []
    for path in [output, DESTINATION / 'metadata.yaml']:
        with path.open('rb') as stream:
            os.fsync(stream.fileno())
        st = path.stat()
        manifest.append({'name': path.name, 'bytes': st.st_size, 'mtime_ns': st.st_mtime_ns, 'sha256': file_digest(path)})
    report = {'verified': True, 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source': str(SOURCE), 'destination': str(DESTINATION), 'source_files': before,
              'files': manifest, 'messages': total, 'topics': len(counts), 'groups': len(stamps),
              'first_log_time_ns': first, 'last_log_time_ns': last, 'topic_counts': dict(counts),
              'exact_raw_message_comparison': True, 'schemas_channels_sequences_and_both_timestamps_equal': True,
              'source_files_unchanged': True, 'uncompressed_chunk_crcs_valid': True, 'metadata_correction': metadata_correction,
              'ordered_message_sha256': native_digest.hexdigest(), 'ros_reader_checks': ros_results,
              'elapsed_s': time.monotonic() - started,
              'scope': 'Exact input/output message equality and ROS readability. Hashes are observations, not security certification.'}
    (DESTINATION / 'merge_verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'phase': 'verified', 'messages': total, 'topics': len(counts), 'groups': len(stamps), 'files': manifest, 'elapsed_s': report['elapsed_s']}), flush=True)


def file_digest_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


if __name__ == '__main__':
    main()
