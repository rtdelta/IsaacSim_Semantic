"""Read cloud message stamps only; report timing coverage against captured joints."""
import json
import bisect
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

path=Path('/root/gpufree-data/semantic/output/lidar_visualizer/20260916_142915_728261_232052/bag')
r=rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=str(path),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
topics=[t.name for t in r.get_all_topics_and_types() if t.type=='sensor_msgs/msg/PointCloud2']
r.set_filter(rosbag2_py.StorageFilter(topics=topics+['/joint_states']))
cloud=get_message('sensor_msgs/msg/PointCloud2');joint=get_message('sensor_msgs/msg/JointState')
out={};ts=[]
while r.has_next():
    topic,data,recorded=r.read_next();m=deserialize_message(data,joint if topic=='/joint_states' else cloud)
    t=m.header.stamp.sec*1000000000+m.header.stamp.nanosec
    if topic=='/joint_states':ts.append(t);continue
    if topic not in out:out[topic]={'frames':[],'frame_ids':[]}
    o=out[topic]
    if m.header.frame_id not in o['frame_ids']:o['frame_ids'].append(m.header.frame_id)
    o['frames'].append({'stamp_ns':t,'record_ns':recorded,'points':int(m.width*m.height)})
ts.sort()
for o in out.values():
    o['frames'].sort(key=lambda x:x['stamp_ns'])
    for f in o['frames']:
        i=bisect.bisect_left(ts,f['stamp_ns'])
        f['nearest_joint_stamp_delta_ns']=min(abs(x-f['stamp_ns']) for x in ts[max(0,i-1):i+1])
print('AUDIT_JSON_START')
print(json.dumps({'joint_range_ns':[ts[0],ts[-1]],'clouds':out}))
