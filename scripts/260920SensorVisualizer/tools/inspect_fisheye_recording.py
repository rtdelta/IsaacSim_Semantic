"""Read-only MCAP/PNG/pose consistency check. Run in ROS 2 Jazzy Python."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def inspect(session):
    session=Path(session)
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag'),storage_id='mcap'),
                rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    counts=defaultdict(int); stamps=defaultdict(set); nonempty=defaultdict(int)
    while reader.has_next():
        topic,data,_=reader.read_next();counts[topic]+=1
        if topic.endswith('/points'):
            msg=deserialize_message(data,types[topic])
            stamps[topic].add(msg.header.stamp.sec*10**9+msg.header.stamp.nanosec)
            nonempty[topic]+=int(msg.width*msg.height>0)
    folder=session/'cameras/fisheye_front'
    rows=[json.loads(line) for line in (folder/'frames.jsonl').read_text().splitlines()]
    matched={topic:sum(any(abs(t-r['simulation_time_ns'])<=1000 for t in times) for r in rows)
             for topic,times in stamps.items()}
    return {'counts':dict(counts),'nonempty_clouds':dict(nonempty),
        'images':len(rows),'all_images_exist':all((folder/r['image']).is_file() for r in rows),
        'image_stamp_unique':len({r['simulation_time_ns'] for r in rows})==len(rows),
        'image_stamp_monotonic':all(a['simulation_time_ns']<b['simulation_time_ns'] for a,b in zip(rows,rows[1:])),
        'max_image_render_pose_error':max((r['render_pose_max_abs_error'] for r in rows),default=None),
        'cloud_exact_timestamp_matches_per_camera_frame':matched,
        'image_time_range':[rows[0]['simulation_time'],rows[-1]['simulation_time']] if rows else [],
        'camera_summary':json.loads((folder/'summary.json').read_text())}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--output');a=p.parse_args()
    result=inspect(a.session)
    text=json.dumps(result,indent=2)+'\n'
    if a.output: Path(a.output).write_text(text)
    print(text)
