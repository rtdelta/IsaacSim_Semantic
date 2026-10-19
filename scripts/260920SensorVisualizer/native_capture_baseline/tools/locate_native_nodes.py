import json
from pathlib import Path
root=Path('/root/isaacsim');out={'extensions':[],'files':[]}
names=['ROS2CameraHelper','ROS2CameraInfoHelper','ROS2RtxLidarHelper','ROS2PublishTransformTree','IsaacComputeTransformTree','ROS2PublishClock','ROS2PublishJointState']
for where in ('exts','extscache'):
 for base in (root/where).iterdir():
  if not base.is_dir() or not any(s in base.name for s in ('ros2','sensors.experimental','sensors.rtx','core.nodes')):continue
  out['extensions'].append(str(base))
  for p in base.rglob('*'):
   if p.is_file() and (p.suffix=='.ogn' and any(n in p.name for n in names) or
                     p.name in ['Ogn'+n+'.py' for n in names]):
    out['files'].append({'path':str(p),'text':p.read_text(errors='replace')[:18000]})
print(json.dumps(out,ensure_ascii=False))
