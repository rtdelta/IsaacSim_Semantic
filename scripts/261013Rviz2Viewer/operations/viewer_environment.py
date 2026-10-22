import json, re, shutil, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
processes=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:argv=p.read_bytes().split(b'\0')
    except OSError:continue
    if not argv:continue
    name=Path(argv[0].decode(errors='replace')).name
    if name in ('Xorg','Xvnc','Xtigervnc','Xvfb'):
        processes.append({'pid':int(p.parent.name),'executable':name,'display':[a.decode() for a in argv if re.fullmatch(rb':\d+(\.\d+)?',a)]})
ros=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','probe','/usr/bin/python3','-c',"import rosbag2_py,rclpy,numpy; from visualization_msgs.msg import MarkerArray; print('available')"],capture_output=True,text=True,timeout=20)
print(json.dumps({'display_sockets':[p.name for p in Path('/tmp/.X11-unix').glob('X*')],'display_processes':processes,'tools':{x:shutil.which(x) for x in ('rviz2','import','xwd','xdpyinfo','xvfb-run')},'ros_exit':ros.returncode,'ros_stdout':ros.stdout.strip(),'ros_stderr':ros.stderr[-1000:]}))
