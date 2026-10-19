"""Use the remote desktop terminal's system Python. Preview must be enabled."""
import argparse
import json
import os
from pathlib import Path
from sensor_visualizer_v03.contracts import DEFAULT


def config(registry):
    lines=['Panels:', '  - Class: rviz_common/Displays','Visualization Manager:',
           '  Global Options:', '    Fixed Frame: world','    Frame Rate: 15','  Displays:',
           '    - Class: rviz_default_plugins/Grid','      Name: Ground Grid','      Enabled: true',
           '    - Class: rviz_default_plugins/TF','      Name: Sensor Poses','      Enabled: true',
           '      Show Axes: true','      Show Names: true','      Marker Scale: 0.4']
    for sensor in registry['lidars']:
        lines += ['    - Class: rviz_default_plugins/PointCloud2','      Name: '+sensor['id'],
          '      Enabled: true','      Topic:','        Value: '+sensor['topic'],
          '        Reliability Policy: Best Effort','        Durability Policy: Volatile','        Depth: 2',
          '      Style: Points','      Size (Pixels): 2','      Decay Time: 0','      Color Transformer: AxisColor']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--session'); p.add_argument('--domain',type=int,default=0); a=p.parse_args()
    if a.session: session=Path(a.session)
    else:
        sessions=sorted(Path(DEFAULT['output_directory']).glob('20*/sensor_registry.json'))
        if not sessions: raise SystemExit('Start Capture once, or specify --session DIRECTORY')
        session=sessions[-1].parent
    registry=json.loads((session/'sensor_registry.json').read_text())
    path=session/'live.rviz'; path.write_text(config(registry))
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'): env.pop(key,None)
    env.update(ROS_DOMAIN_ID=str(a.domain),RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    command=['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec rviz2 -d "$1" --ros-args -p use_sim_time:=true','sv03-rviz',str(path)]
    os.execve(command[0],command,env)
