"""Executed by installed system ROS Python. Reads only the finished unified bag."""
from collections import Counter,defaultdict
import hashlib,io,json,math
from pathlib import Path
import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

session=Path('/root/gpufree-data/semantic/output/sensor_visualizer/20260923_102450_024594_6ccb02')
reader=rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
types={t.name:t.type for t in reader.get_all_topics_and_types()};classes={n:get_message(t) for n,t in types.items()}
counts=Counter();stamps=defaultdict(list);frames=defaultdict(set);clouds=defaultdict(lambda:dict(points=0,empty_frames=0,nonfinite_points=0,min_points=None,max_points=0))
images={};edges=Counter();joints=defaultdict(list);positions=[];orientations=[];clock=[];first=last=None
def ns(t):return t.sec*10**9+t.nanosec
def image_stat(msg):
    with Image.open(io.BytesIO(bytes(msg.data))) as im:
        array=np.asarray(im.convert('RGB'))
        return dict(width=im.width,height=im.height,mean_rgb=array.mean(axis=(0,1)).tolist(),std_rgb=array.std(axis=(0,1)).tolist())
while reader.has_next():
    topic,data,t=reader.read_next();counts[topic]+=1;first=t if first is None else min(first,t);last=t if last is None else max(last,t)
    msg=deserialize_message(data,classes[topic]);kind=types[topic]
    if hasattr(msg,'header'):stamps[topic].append(ns(msg.header.stamp));frames[topic].add(msg.header.frame_id)
    if kind=='sensor_msgs/msg/PointCloud2':
        row=clouds[topic];n=msg.width*msg.height;row['points']+=n;row['empty_frames']+=int(n==0)
        row['min_points']=n if row['min_points'] is None else min(n,row['min_points']);row['max_points']=max(n,row['max_points'])
        if msg.point_step==12 and n:
            xyz=np.frombuffer(msg.data,dtype='<f4').reshape(-1,3)
            row['nonfinite_points']+=int((~np.isfinite(xyz).all(axis=1)).sum())
    elif kind=='sensor_msgs/msg/CompressedImage':
        if topic not in images:images[topic]=dict(first=image_stat(msg),format=msg.format)
        images[topic]['last_data']=bytes(msg.data);images[topic]['last_format']=msg.format
    elif kind=='tf2_msgs/msg/TFMessage':
        for tf in msg.transforms:edges[(tf.header.frame_id,tf.child_frame_id)]+=1
    elif kind=='sensor_msgs/msg/JointState':
        for name,value in zip(msg.name,msg.position):joints[name].append(value)
    elif topic=='/excavator/root_pose':
        positions.append([getattr(msg.pose.position,x) for x in 'xyz']);orientations.append([getattr(msg.pose.orientation,x) for x in 'xyzw'])
    elif topic=='/clock':clock.append(ns(msg.clock))
for row in images.values():
    with Image.open(io.BytesIO(row.pop('last_data'))) as im:
        array=np.asarray(im.convert('RGB'));row['last']=dict(width=im.width,height=im.height,mean_rgb=array.mean(axis=(0,1)).tolist(),std_rgb=array.std(axis=(0,1)).tolist())
timings={}
for topic,ts in stamps.items():
    gaps=Counter(b-a for a,b in zip(ts,ts[1:]));timings[topic]=dict(first_ns=min(ts),last_ns=max(ts),unique=len(set(ts)),steps_ns=dict(gaps),frames=sorted(frames[topic]))
camera_sets={topic:set(stamps[topic]) for topic in stamps if topic.endswith('/image_raw/compressed')}
reference=next(iter(camera_sets.values()))
alignment={topic:dict(missing_camera_times=len(reference-set(ts)),extra_times=len(set(ts)-reference),
    missing_ns=sorted(reference-set(ts)),extra_ns=sorted(set(ts)-reference),
    max_nearest_error_ns=max(min(abs(v-t) for v in reference) for t in ts)) for topic,ts in stamps.items()
           if types[topic]=='sensor_msgs/msg/PointCloud2' or topic.startswith('/camera/')}
print(json.dumps(dict(counts=dict(counts),message_count=sum(counts.values()),topic_count=len(types),bag_record_first_ns=first,bag_record_last_ns=last,
    clock=dict(first_ns=min(clock),last_ns=max(clock),steps_ns=dict(Counter(b-a for a,b in zip(clock,clock[1:])))),
    timings=timings,alignment=alignment,clouds=dict(clouds),images=images,
    tf_edges=[dict(parent=a,child=b,count=n) for (a,b),n in edges.items()],
    joint_degrees={k:dict(min=math.degrees(min(v)),max=math.degrees(max(v))) for k,v in joints.items()},
    root_position_bounds=dict(min=np.min(positions,axis=0).tolist(),max=np.max(positions,axis=0).tolist()),
    root_quaternion_bounds=dict(min=np.min(orientations,axis=0).tolist(),max=np.max(orientations,axis=0).tolist()))))
