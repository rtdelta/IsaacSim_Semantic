"""Read only the capture tree and installed merge tool interfaces."""
import json
import shutil
import subprocess
from pathlib import Path

root = Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer')
bags = []
for bag in root.glob('*/capture/captures/*/bag_unified'):
    bags.append({'path': str(bag), 'mtime_ns': bag.stat().st_mtime_ns,
                 'files': [{'name': p.name, 'bytes': p.stat().st_size,
                            'mtime_ns': p.stat().st_mtime_ns}
                           for p in sorted(bag.iterdir()) if p.is_file()],
                 'siblings': [p.name for p in bag.parent.iterdir()]})
print(json.dumps({'captures': sorted(bags, key=lambda b: b['mtime_ns'], reverse=True),
                  'free_bytes': shutil.disk_usage(root).free}))
probe = r'''
import importlib.util, inspect, json
import rosbag2_py, struct
result = {'rosbag2_path': rosbag2_py.__file__,
          'mcap_available': importlib.util.find_spec('mcap') is not None,
          'yaml_available': importlib.util.find_spec('yaml') is not None}
for name in ['SequentialReader', 'SequentialWriter', 'StorageOptions', 'ConverterOptions', 'TopicMetadata']:
    cls = getattr(rosbag2_py, name)
    result[name] = cls.__doc__
    if name == 'SequentialWriter':
        result['write_doc'] = cls.write.__doc__
    if name == 'SequentialReader':
        result['read_next_doc'] = cls.read_next.__doc__
print(json.dumps(result))
source = '/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300/capture/captures/20261013_142524_685978_f13b03ee/bag_unified'
reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=source, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
first = reader.read_next()
topic = reader.get_all_topics_and_types()[0]
print(json.dumps({'reader_methods': [x for x in dir(reader) if not x.startswith('_')],
                  'tuple_length': len(first), 'tuple_types': [type(x).__name__ for x in first],
                  'first_topic': first[0], 'first_times': list(first[2:]),
                  'topic_fields': [x for x in dir(topic) if not x.startswith('_')]}))
with open(source + '/bag_unified_0.mcap', 'rb') as stream:
    assert stream.read(8) == b'\x89MCAP0\r\n'
    while True:
        head = stream.read(9)
        op, size = struct.unpack('<BQ', head)
        if op == 6:
            fixed = stream.read(28)
            n = struct.unpack('<I', stream.read(4))[0]
            compression = stream.read(n).decode()
            print(json.dumps({'first_chunk_compression': compression, 'first_chunk_record_size': size}))
            break
        stream.seek(size, 1)
'''
response = subprocess.run(['bash', '-c', 'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B -c "$1"', 'mcap-preflight', probe], capture_output=True, text=True, timeout=30)
print(json.dumps({'tool_probe_exit_code': response.returncode, 'stdout': response.stdout, 'stderr': response.stderr}))
matches = []
for entry in Path('/proc').iterdir():
    if not entry.name.isdecimal():
        continue
    try:
        cmd = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        if str(root) in cmd and ('merge' in cmd or 'convert' in cmd):
            matches.append({'pid': int(entry.name), 'command': cmd[:400]})
    except (OSError, PermissionError):
        pass
print(json.dumps({'existing_merge_processes': matches}))
