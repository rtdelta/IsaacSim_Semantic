import subprocess,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
out=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
code=r'''
import json,hashlib
from pathlib import Path
import rosbag2_py,numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
out=Path(__import__('sys').argv[1]);groups=[json.loads(l) for l in (out/'groups.jsonl').read_text().splitlines()]
reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(out/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()};rows=[]
while reader.has_next():
 topic,data,t=reader.read_next()
 if not(topic.endswith('/image_raw') or topic.endswith('/points')):continue
 msg=deserialize_message(data,types[topic]);stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
 if topic.endswith('/image_raw'):
  c=3 if msg.encoding=='rgb8' else 4;a=np.ndarray((msg.height,msg.width,c),dtype='u1',buffer=msg.data,strides=(msg.step,c,1))[:,:,:3]
  h=hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest();match=[g['group'] for g in groups if g['images'][topic]['sha256']==h]
 else:
  f={x.name:x for x in msg.fields};a=np.empty((msg.height,msg.width,3),dtype='<f4')
  for i,n in enumerate(('x','y','z')):a[:,:,i]=np.ndarray((msg.height,msg.width),dtype='>f4' if msg.is_bigendian else '<f4',buffer=msg.data,offset=f[n].offset,strides=(msg.row_step,msg.point_step))
  h=hashlib.sha256(a.tobytes()).hexdigest();match=[g['group'] for g in groups if g['lidars'][topic]['sha256_xyz']==h]
 rows.append({'topic':topic,'stamp_ns':stamp,'matches_groups':match,'sha256':h})
cycles=json.loads((out/'native_cycles.json').read_text());summary={'messages':rows,'cycles':[{k:c.get(k) for k in ('index','sdk_trigger_time','sdk_capture_time','native_time_s','begin_sim_time')} for c in cycles]}
(out/'diagnostic_message_alignment.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
'''
p=subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -c "$1" "$2"','nc003',code,str(out)],capture_output=True,text=True)
print(p.stdout);print(p.stderr);raise SystemExit(p.returncode)
