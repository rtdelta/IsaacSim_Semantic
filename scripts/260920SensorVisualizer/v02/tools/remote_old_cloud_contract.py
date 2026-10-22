from pathlib import Path
import os
import json
import subprocess
base=Path('/root/gpufree-data/semantic/output/sensor_visualizer')
bags=sorted(base.glob('20*/bag_unified/metadata.yaml'))
if not bags: raise RuntimeError('No prior v01 unified bag')
script="""import sys,json,rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2
r=rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=sys.argv[1],storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
while r.has_next():
 t,d,s=r.read_next()
 if t.endswith('/points'):
  m=deserialize_message(d,PointCloud2)
  print(json.dumps({'topic':t,'point_step':m.point_step,'fields':[(f.name,f.offset,f.datatype) for f in m.fields]}));break
"""
env=os.environ.copy()
for k in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','CONDA_PREFIX','VIRTUAL_ENV'): env.pop(k,None)
p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -c "$1" "$2"','sv02-schema',script,str(bags[-1].parent)],env=env,capture_output=True,text=True,timeout=30)
print(json.dumps({'bag':str(bags[-1].parent),'stdout':p.stdout,'stderr':p.stderr,'returncode':p.returncode}))
