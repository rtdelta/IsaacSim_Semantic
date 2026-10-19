"""Decode only native JointState after the recorded motion experiment."""
import json,math
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import JointState
out=Path('/root/gpufree-data/semantic/output/native_capture_baseline/wave_ordinary_20261011_124852/D_moving')
reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(out/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
ranges={};last={};count=0
while reader.has_next():
 topic,data,t=reader.read_next()
 if topic!='/joint_states':continue
 msg=deserialize_message(data,JointState);count+=1
 for name,pos in zip(msg.name,msg.position):
  deg=math.degrees(pos);v=ranges.setdefault(name,[deg,deg]);v[0]=min(v[0],deg);v[1]=max(v[1],deg);last[name]=deg
result={'messages':count,'ranges_deg':ranges,'last_deg':last,'limit':'Reference base pose is constant; this run verifies joint motion, not base translation/rotation.'}
Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline/reports/joint_motion.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
