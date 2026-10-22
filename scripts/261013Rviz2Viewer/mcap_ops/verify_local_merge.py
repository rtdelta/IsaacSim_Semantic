"""Compare the downloaded merged MCAP against the existing local source segments."""
import collections
import datetime
import hashlib
import itertools
import json
import os
import struct
import sys
from pathlib import Path

import yaml
from verify_mcap_records import file_digest, messages, update_ros_digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pull_mcap as connection
from cloud_ops.audit import verify_file


def main():
    source = connection.DESTINATION / 'bag_unified'
    destination = connection.DESTINATION / 'bag_merged'
    manifest = json.loads((destination / 'source_manifest.json').read_text(encoding='utf-8'))
    report = json.loads((destination / 'merge_verification.json').read_text(encoding='utf-8'))
    receipt = json.loads((destination / 'transfer_receipt.json').read_text(encoding='utf-8'))
    audit = connection.Audit(connection.private_directory(Path(os.environ['LOCALAPPDATA']) / 'CloudInstanceOps'),
        connection.Redactor(), '20261013-merge-single06-300', 'Independent local message and file hash verification',
        'local-merge-verification', 'local-project-files-only')
    try:
        transfer_audit = verify_file(receipt['audit_log'])
        assert transfer_audit['integrity'] == 'valid' and transfer_audit['completion'] == 'recorded'
        results = []
        for item in manifest['files']:
            path = destination / item['name']
            actual = file_digest(path)
            assert actual == item['sha256'] and path.stat().st_size == item['bytes']
            results.append({'name': item['name'], 'bytes': path.stat().st_size, 'sha256': actual, 'matches_remote': True})
        for item in report['source_files']:
            path = source / item['name']
            assert path.stat().st_size == item['bytes'] and file_digest(path) == item['sha256']
        old_messages = itertools.chain.from_iterable(messages(source / name) for name in ['bag_unified_0.mcap', 'bag_unified_1.mcap', 'bag_unified_2.mcap'])
        new_messages = messages(destination / 'bag_merged_0.mcap')
        counts, group_ids, group_stamps = collections.Counter(), [], []
        digest = hashlib.sha256()
        n = 0
        for old, new in itertools.zip_longest(old_messages, new_messages):
            assert old is not None and new is not None and old == new, 'Local source/output message mismatch at ' + str(n)
            channel, sequence, log_time, publish_time, payload = new
            topic = channel[0]
            counts[topic] += 1
            update_ros_digest(digest, topic, log_time, payload)
            if topic == '/sensor_visualizer/frame_index':
                assert payload[:2] == b'\x00\x01'
                length = struct.unpack_from('<I', payload, 4)[0]
                assert payload[8 + length - 1] == 0
                index = json.loads(payload[8:8 + length - 1])
                group_ids.append(index['group_id'])
                group_stamps.append(index['simulation_time_ns'])
                assert index['simulation_time_ns'] == log_time == publish_time
            n += 1
        assert n == 9006 and len(counts) == 32 and group_ids == list(range(300))
        assert all(b - a == 100_000_000 for a, b in zip(group_stamps, group_stamps[1:]))
        assert dict(counts) == report['topic_counts']
        assert digest.hexdigest() == report['ros_reader_checks'][0]['ordered_content_sha256']
        metadata = yaml.safe_load((destination / 'metadata.yaml').read_text(encoding='utf-8'))['rosbag2_bagfile_information']
        assert metadata['relative_file_paths'] == ['bag_merged_0.mcap']
        assert metadata['message_count'] == metadata['files'][0]['message_count'] == n
        assert not list(destination.glob('*.part')) and not (destination / '.transfer_parts').exists()
        verification = {'verified': True, 'verified_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        'files': results, 'messages': n, 'topics': len(counts), 'groups': len(group_ids),
                        'group_ids': {'first': group_ids[0], 'last': group_ids[-1], 'contiguous': True},
                        'group_interval_ns': 100_000_000, 'topic_counts': dict(counts),
                        'exact_comparison_with_local_source_segments': True,
                        'schema_channel_sequence_log_time_publish_time_payload_equal': True,
                        'ordered_ros_content_sha256': digest.hexdigest(), 'transfer_audit': transfer_audit,
                        'audit_log': str(audit.path), 'source_files_retained': True}
        (destination / 'local_verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
        audit.event('artifact.local_merge.verified', **verification)
        audit.finish('succeeded', messages=n, topics=len(counts), groups=len(group_ids))
        assert verify_file(audit.path)['integrity'] == 'valid'
        print(json.dumps({'verified': True, 'messages': n, 'topics': len(counts), 'groups': len(group_ids),
                          'destination': str(destination), 'audit_log': str(audit.path)}))
    except BaseException as exc:
        if not audit.closed:
            audit.finish('failed', error_type=type(exc).__name__, error=str(exc))
        raise


if __name__ == '__main__':
    main()
