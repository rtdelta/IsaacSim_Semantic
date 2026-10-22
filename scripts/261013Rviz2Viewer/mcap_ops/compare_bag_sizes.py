"""Read the two local delivered bags and attribute their size difference."""
import collections
import json
import struct
from pathlib import Path

from verify_mcap_records import messages

ROOT = Path(__file__).resolve().parents[3]
BAGS = {
    'native_20261012': ROOT / 'output/20261012_scene18_native_rt2_300_handoff/delivery_300/bag/bag_0.mcap',
    'single06_20261013_merged': ROOT / 'output/20261013_scene18_single06_300_mcap/bag_merged/bag_merged_0.mcap',
}


class Cdr:
    def __init__(self, data):
        assert data[:2] == b'\x00\x01', 'Expected CDR little endian'
        self.data, self.offset = data, 4

    def u32(self):
        self.offset += -(self.offset - 4) % 4
        value = struct.unpack_from('<I', self.data, self.offset)[0]
        self.offset += 4
        return value

    def u8(self):
        value = self.data[self.offset]
        self.offset += 1
        return value

    def string(self):
        size = self.u32()
        end = self.offset + size
        assert self.data[end - 1] == 0
        value = self.data[self.offset:end - 1].decode()
        self.offset = end
        return value

    def header(self):
        self.u32()
        self.u32()
        return self.string()

    def byte_array(self):
        size = self.u32()
        start = self.offset
        self.offset += size
        assert self.offset <= len(self.data)
        return start, size


def analyze(path):
    topics = {}
    total = 0
    for channel, sequence, log_time, publish_time, data in messages(path):
        name, _, _, schema = channel
        kind = schema[0].decode()
        topic = topics.setdefault(name, {'type': kind, 'messages': 0, 'serialized_bytes': 0,
                                        'data_bytes': 0, 'formats': set(), 'dimensions': set(),
                                        'point_layouts': set(), 'points_total': 0,
                                        'min_points': None, 'max_points': None})
        assert topic['type'] == kind
        topic['messages'] += 1
        topic['serialized_bytes'] += len(data)
        total += 1
        if kind in ('sensor_msgs/msg/Image', 'sensor_msgs/msg/CompressedImage', 'sensor_msgs/msg/PointCloud2'):
            reader = Cdr(data)
            reader.header()
            if kind == 'sensor_msgs/msg/Image':
                height, width = reader.u32(), reader.u32()
                encoding = reader.string()
                bigendian, step = reader.u8(), reader.u32()
                _, size = reader.byte_array()
                assert height * step == size
                topic['formats'].add(encoding)
                topic['dimensions'].add((width, height))
                topic['data_bytes'] += size
            elif kind == 'sensor_msgs/msg/CompressedImage':
                encoding = reader.string()
                start, size = reader.byte_array()
                assert data[start:start + 8] == b'\x89PNG\r\n\x1a\n'
                assert data[start + 12:start + 16] == b'IHDR'
                width, height, depth, color = struct.unpack_from('>IIBB', data, start + 16)
                assert depth == 8 and color == 2, 'Expected 8-bit RGB PNG'
                topic['formats'].add(encoding)
                topic['dimensions'].add((width, height))
                topic['data_bytes'] += size
            else:
                height, width = reader.u32(), reader.u32()
                fields = []
                for _ in range(reader.u32()):
                    fields.append((reader.string(), reader.u32(), reader.u8(), reader.u32()))
                bigendian, point_step, row_step = reader.u8(), reader.u32(), reader.u32()
                _, size = reader.byte_array()
                dense = reader.u8()
                assert size == row_step * height and row_step == point_step * width
                topic['point_layouts'].add((tuple(fields), point_step, bigendian))
                n = width * height
                topic['points_total'] += n
                topic['min_points'] = n if topic['min_points'] is None else min(topic['min_points'], n)
                topic['max_points'] = n if topic['max_points'] is None else max(topic['max_points'], n)
                topic['data_bytes'] += size
    categories = {}
    for name, topic in topics.items():
        for key in ['formats', 'dimensions', 'point_layouts']:
            topic[key] = sorted(topic[key])
        kind = topic['type']
        category = 'images' if kind in ('sensor_msgs/msg/Image', 'sensor_msgs/msg/CompressedImage') else 'point_clouds' if kind == 'sensor_msgs/msg/PointCloud2' else 'other'
        group = categories.setdefault(category, {'messages': 0, 'serialized_bytes': 0, 'data_bytes': 0, 'points_total': 0})
        for key in group:
            group[key] += topic[key]
    serialized = sum(x['serialized_bytes'] for x in categories.values())
    return {'path': str(path), 'file_bytes': path.stat().st_size,
            'file_GB': path.stat().st_size / 1e9, 'file_GiB': path.stat().st_size / 2**30,
            'messages': total, 'topics': len(topics), 'categories': categories,
            'container_overhead_bytes': path.stat().st_size - serialized, 'per_topic': topics}


def main():
    results = {}
    for label, path in BAGS.items():
        results[label] = analyze(path)
        print(json.dumps({'bag': label, **{k: v for k, v in results[label].items() if k != 'per_topic'}}, ensure_ascii=False), flush=True)
    old, new = results.values()
    results['difference'] = {'file_bytes_saved': old['file_bytes'] - new['file_bytes'],
                             'file_reduction_percent': 100 * (1 - new['file_bytes'] / old['file_bytes']),
                             'categories_bytes_saved': {name: old['categories'][name]['serialized_bytes'] - new['categories'][name]['serialized_bytes'] for name in old['categories']}}
    original_segments_bytes = sum(p.stat().st_size for p in (BAGS['single06_20261013_merged'].parent.parent / 'bag_unified').glob('*.mcap'))
    results['merge_only'] = {'input_segments_bytes': original_segments_bytes, 'output_bytes': new['file_bytes'],
                             'bytes_saved': original_segments_bytes - new['file_bytes']}
    report = ROOT / 'scripts/261013Rviz2Viewer/reports/mcap_size_comparison.json'
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'difference': results['difference'], 'merge_only': results['merge_only'], 'report': str(report)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
