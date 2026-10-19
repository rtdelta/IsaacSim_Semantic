import hashlib, json, os, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
files={}
for group in ('sensor_visualizer/*.py','config/*.json','tools/*.py','tools/*.sh','README.md'):
    for p in root.glob(group):
        raw=p.read_bytes()
        files[str(p.relative_to(root))]=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()
processes=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        name=(p/'comm').read_text().strip()
        if name=='kit': processes.append({'pid':int(p.name),'name':name})
    except OSError: pass
env=os.environ.copy()
for k in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','AMENT_PREFIX_PATH','CMAKE_PREFIX_PATH','CONDA_PREFIX','VIRTUAL_ENV'): env.pop(k,None)
code="import json,rosbag2_py,numpy; from sensor_msgs.msg import CameraInfo; from rclpy.serialization import serialize_message; print(json.dumps({'rosbag':True,'numpy':numpy.__version__,'topic_doc':rosbag2_py.TopicMetadata.__init__.__doc__}))"
r=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash; exec /usr/bin/python3 -c "$1"','probe',code],env=env,text=True,capture_output=True,timeout=20)
cfg=json.loads((root/'config/sensors.json').read_text())
print(json.dumps({'files':files,'processes':processes,'ros_probe':{'code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},'cameras':cfg.get('cameras'),'output':cfg.get('output_directory')}))
