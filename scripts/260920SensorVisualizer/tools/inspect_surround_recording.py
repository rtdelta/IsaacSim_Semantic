"""Read-only verification of four-camera groups against their ROS2 MCAP."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def inspect(session):
    session=Path(session)
    groups=[json.loads(s) for s in (session/'capture_index.jsonl').read_text().splitlines()]
    ids=list(groups[0]['cameras'])
    cameras={cid:[json.loads(s) for s in (session/'cameras'/cid/'frames.jsonl').read_text().splitlines()] for cid in ids}
    checks={'nonempty_groups':bool(groups),'four_cameras':len(ids)==4,
            'equal_camera_counts':all(len(v)==len(groups) for v in cameras.values()),
            'monotonic_groups':all(a['simulation_time_ns']<b['simulation_time_ns'] for a,b in zip(groups,groups[1:])),
            'same_camera_timestamps':True,'png_1920x1080':True,'same_robot_state':True}
    origin_errors={cid:0. for cid in ids};pose_error=0.
    for group in groups:
        states=[]
        for cid,entry in group['cameras'].items():
            row=cameras[cid][entry['frame_index']]
            checks['same_camera_timestamps'] &= row['simulation_time_ns']==group['simulation_time_ns']
            with (session/entry['image']).open('rb') as stream: header=stream.read(24)
            checks['png_1920x1080'] &= header[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',header[16:24])==(1920,1080)
            states.append((row['root_position'],row['root_orientation_xyzw'],row['joint_positions_rad']))
            pose_error=max(pose_error,row['render_pose_max_abs_error'])
            lidar='MyAiry_'+('back' if cid=='rear' else cid)
            error=sum((a-b)**2 for a,b in zip(row['camera_usd_to_world'][3][:3],row['lidar_to_world'][lidar][3][:3]))**.5
            origin_errors[cid]=max(origin_errors[cid],error)
        checks['same_robot_state'] &= all(s==states[0] for s in states[1:])
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    counts=defaultdict(int);stamps=defaultdict(set);nonempty=defaultdict(int)
    while reader.has_next():
        topic,data,_=reader.read_next();counts[topic]+=1
        if topic.endswith('/points'):
            msg=deserialize_message(data,types[topic])
            stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
            if msg.width*msg.height:
                stamps[topic].add(stamp);nonempty[topic]+=1
    matches={topic:sum(any(abs(t-g['simulation_time_ns'])<=1000 for t in times) for g in groups)
             for topic,times in stamps.items()}
    checks['thirteen_lidars']=len(matches)==13
    checks['every_group_has_thirteen_clouds']=len(matches)==13 and all(v==len(groups) for v in matches.values())
    checks['origins_coincide']=max(origin_errors.values())<1e-5
    checks['render_pose_matches']=pose_error<2e-3
    return {'passed':all(checks.values()),'checks':checks,'session':str(session),
            'groups':len(groups),'images':sum(len(v) for v in cameras.values()),'topic_counts':dict(counts),
            'matched_nonempty_cloud_timestamps':matches,'max_origin_errors_m':origin_errors,
            'max_render_pose_matrix_error':pose_error,
            'capture_summary':json.loads((session/'capture_summary.json').read_text())}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--output');a=p.parse_args()
    result=inspect(a.session);text=json.dumps(result,indent=2)+'\n'
    if a.output: Path(a.output).write_text(text)
    print(text)
    raise SystemExit(0 if result['passed'] else 1)
