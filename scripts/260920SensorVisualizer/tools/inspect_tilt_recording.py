"""Verify saved body tilt, ROS root pose/TF and actual terrain LiDAR returns."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import struct
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from inspect_surround_recording import inspect


def ns(stamp):return stamp.sec*10**9+stamp.nanosec
def qxy(q):return [q.x,q.y,q.z,q.w]
def vxyz(v):return [v.x,v.y,v.z]
def qm(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def rotate(q,v):return qm(qm(q,[*v,0]),[-q[0],-q[1],-q[2],q[3]])[:3]
def qe(a,b):return min(max(abs(x-y) for x,y in zip(a,b)),max(abs(x+y) for x,y in zip(a,b)))


def verify(session):
    folder=Path(session);result=inspect(folder)
    frames=[json.loads(l) for l in (folder/'cameras/front/frames.jsonl').read_text().splitlines()]
    keyed={round(f['simulation_time_ns']/1000):f for f in frames}
    poses={};transforms=defaultdict(dict);terrain={'positive':0,'negative':0,'sampled':0}
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(folder/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    while reader.has_next():
        topic,raw,_=reader.read_next()
        if topic not in ['/tf','/excavator/root_pose'] and not topic.endswith('/points'):continue
        msg=deserialize_message(raw,types[topic])
        if topic=='/tf':
            for t in msg.transforms:
                key=round(ns(t.header.stamp)/1000)
                if key in keyed:transforms[key][t.child_frame_id]=(t.header.frame_id,vxyz(t.transform.translation),qxy(t.transform.rotation))
        elif topic=='/excavator/root_pose':
            key=round(ns(msg.header.stamp)/1000)
            if key in keyed:poses[key]=(vxyz(msg.pose.position),qxy(msg.pose.orientation))
        else:
            key=round(ns(msg.header.stamp)/1000);frame=keyed.get(key)
            if frame is None:continue
            matrix=frame['lidar_to_world'].get(msg.header.frame_id)
            if matrix is None:continue
            fields={f.name:f for f in msg.fields}
            if any(n not in fields or fields[n].datatype!=7 for n in ('x','y','z')):continue
            endian='>' if msg.is_bigendian else '<'
            for index in range(0,msg.width*msg.height,30):
                row,col=divmod(index,msg.width);start=row*msg.row_step+col*msg.point_step
                p=[struct.unpack_from(endian+'f',msg.data,start+fields[n].offset)[0] for n in ('x','y','z')]
                if not all(math.isfinite(x) for x in p):continue
                w=[sum(p[i]*matrix[i][j] for i in range(3))+matrix[3][j] for j in range(3)]
                # Central ground patch excludes the machine footprint and far background.
                x,y,z=w
                if -17<x<15 and -15<y<18 and math.hypot((x+1.8)/3.8,(y-1.5)/2.5)>1.7 and -.6<z<.6:
                    terrain['sampled']+=1
                    terrain['positive']+=int(z>.12)
                    terrain['negative']+=int(z<-.12)
    pose_error=quat_error=tf_pos_error=tf_quat_error=0.;matched_tf=0
    for key,frame in keyed.items():
        if key in poses:
            p,q=poses[key]
            pose_error=max(pose_error,max(abs(a-b) for a,b in zip(p,frame['root_position'])))
            quat_error=max(quat_error,qe(q,frame['root_orientation_xyzw']))
        tree=transforms.get(key,{})
        h=tree.get('swing_horizontal_coordinate');s=tree.get('swing_coordinate')
        if h and s and h[0]=='world' and s[0]=='swing_horizontal_coordinate':
            p=[a+b for a,b in zip(h[1],rotate(h[2],s[1]))];q=qm(h[2],s[2]);matched_tf+=1
            tf_pos_error=max(tf_pos_error,max(abs(a-b) for a,b in zip(p,frame['root_position'])))
            tf_quat_error=max(tf_quat_error,qe(q,frame['root_orientation_xyzw']))
    extra={'all_frames_have_tilt_metadata':all(f.get('base_control') for f in frames),
           'tilt_varies_in_saved_frames':max(f['base_control']['tilt_offsets']['pitch']['angle'] for f in frames)-min(f['base_control']['tilt_offsets']['pitch']['angle'] for f in frames)>1,
           # Recorder subscription startup can miss the first volatile Pose
           # message. TF and image metadata must still cover EVERY image pose.
           'available_root_poses_match_images':bool(poses) and max(pose_error,quat_error)<2e-5,
           'interior_frames_have_root_pose':all(key in poses for key in sorted(keyed)[1:]),
           'tf_matches_images':matched_tf==len(frames) and max(tf_pos_error,tf_quat_error)<2e-5,
           'terrain_hills_and_pits_have_returns':min(terrain['positive'],terrain['negative'])>20,
           'terrain_metadata_saved':bool(json.loads((folder/'session.json').read_text())['scene'].get('terrain'))}
    result['checks'].update(extra);result['passed']=all(result['checks'].values())
    result.update(root_pose_matches=len(poses),tf_matches=matched_tf,
        root_pose_topic_covers_every_image=len(poses)==len(frames),
        root_pose_missing_image_stamps=[f['simulation_time_ns'] for key,f in keyed.items() if key not in poses],
        root_pose_position_error_m=pose_error,root_pose_quaternion_error=quat_error,
        tf_position_error_m=tf_pos_error,tf_quaternion_error=tf_quat_error,terrain_return_samples=terrain)
    result['boundary_notes']=([] if len(poses)==len(frames) else [
        'The first image timestamp has no supplemental volatile /excavator/root_pose message. '
        'Its full actual pose is present in /tf and the image metadata; no interpolation or fabricated message was added.'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--output',required=True);a=p.parse_args()
    r=verify(a.session);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
    raise SystemExit(0 if r['passed'] else 1)
