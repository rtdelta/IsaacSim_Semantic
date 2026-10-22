"""Read state and TF messages from existing bags; does not write on remote."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

root=Path('/root/gpufree-data/semantic/output/lidar_visualizer')
out={}
for name in ['20260915_154455_511470_a457ad','20260916_140449_684570_be7d0d','20260916_142915_728261_232052']:
    base=root/name
    if not (base/'bag').exists(): continue
    r=rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(base/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:t.type for t in r.get_all_topics_and_types()}
    classes={k:get_message(v) for k,v in types.items() if k in ['/joint_states','/tf','/tf_static','/excavator/root_pose']}
    r.set_filter(rosbag2_py.StorageFilter(topics=list(classes)))
    result={'path':str(base),'counts':Counter(),'tf':{},'states':[],'root_first':None}
    while r.has_next():
        topic,data,recorded=r.read_next();msg=deserialize_message(data,classes[topic]);result['counts'][topic]+=1
        if topic=='/joint_states':
            q=dict(zip(msg.name,[math.degrees(v) for v in msg.position]));t=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9
            result['states'].append({'t':t,'q_deg':q})
        if topic=='/excavator/root_pose' and result['root_first'] is None:
            p=msg.pose.position;q=msg.pose.orientation
            result['root_first']={'t':msg.header.stamp.sec+msg.header.stamp.nanosec/1e9,'frame':msg.header.frame_id,'xyz':[p.x,p.y,p.z],'quat_xyzw':[q.x,q.y,q.z,q.w]}
        if topic in ['/tf','/tf_static']:
            for tf in msg.transforms:
                key=tf.header.frame_id+' -> '+tf.child_frame_id;t=tf.header.stamp.sec+tf.header.stamp.nanosec/1e9
                p=tf.transform.translation;q=tf.transform.rotation
                item={'t':t,'xyz':[p.x,p.y,p.z],'quat_xyzw':[q.x,q.y,q.z,q.w]}
                if key not in result['tf']: result['tf'][key]={'count':0,'first':item,'last':item,'min_xyz':item['xyz'][:],'max_xyz':item['xyz'][:]}
                dest=result['tf'][key];dest['count']+=1
                if t<dest['first']['t']:dest['first']=item
                if t>dest['last']['t']:dest['last']=item
                dest['min_xyz']=[min(x,y) for x,y in zip(dest['min_xyz'],item['xyz'])];dest['max_xyz']=[max(x,y) for x,y in zip(dest['max_xyz'],item['xyz'])]
    result['states'].sort(key=lambda x:x['t'])
    if result['states']:
        result['closest_documented_bind']=min(result['states'],key=lambda s:sum((s['q_deg'][k]-v)**2 for k,v in [('boom',37.1667),('arm',-85)]))
    out[name]=result
print('AUDIT_JSON_START')
print(json.dumps(out))
