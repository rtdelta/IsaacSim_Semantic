"""Static inspection of already installed ROS node sources and schemas."""
import json
from pathlib import Path
root=Path('/root/isaacsim')
patterns=['isaacsim.ros2.bridge-*','isaacsim.core.nodes-*','isaacsim.sensors.experimental.rtx-*']
selected=['ROS2CameraHelper','ROS2CameraInfoHelper','ROS2RtxLidarHelper','ROS2PublishTransformTree',
 'IsaacComputeTransformTree','ROS2PublishClock','IsaacReadSimulationTime','ROS2PublishJointState']
out=[]
for pattern in patterns:
 for base in (root/'extscache').glob(pattern):
  for p in base.rglob('*'):
   if p.is_file() and p.suffix in ('.ogn','.py') and (any(s in p.name for s in selected) or p.name in ('sensor.py','lidar.py')):
    text=p.read_text(errors='replace')
    if len(text)>35000 and p.suffix=='.py':
     lines=text.splitlines();hits=[i for i,x in enumerate(lines) if any(s in x for s in ['class LidarSensor','def attach_writer','def initialize','def set_tick_rate'])]
     text='\n'.join('\n'.join(lines[max(0,i-4):i+50]) for i in hits)
    out.append({'path':str(p),'text':text})
print(json.dumps({'sources':out},ensure_ascii=False))
