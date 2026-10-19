import subprocess,json
from pathlib import Path
ros=Path('/opt/ros/jazzy')
commands=[['ros2','bag','play','--help'],['ros2','pkg','prefix','rviz2']]
results=[]
for argv in commands:
 r=subprocess.run(['bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','probe',*argv],capture_output=True,text=True,timeout=20)
 results.append({'argv':argv,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
for relative in ('share/rosbag2_interfaces/srv/Burst.srv','share/rosbag2_interfaces/srv/PlayNext.srv','share/rosbag2_transport/package.xml'):
 p=ros/relative
 if p.exists():results.append({'file':relative,'text':p.read_text()[:6000]})
print(json.dumps(results))
