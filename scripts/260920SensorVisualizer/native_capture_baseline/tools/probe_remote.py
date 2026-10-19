"""Read existing native APIs/tools and scoped process state. No imports in Isaac."""
import hashlib,json,os,subprocess
from pathlib import Path
isaac=Path('/root/isaacsim')
project=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
names=['ROS2CameraHelper','ROS2CameraInfoHelper','ROS2RtxLidarHelper','ROS2PublishTransformTree',
 'IsaacComputeTransformTree','ROS2PublishClock','IsaacReadSimulationTime','IsaacCreateRenderProduct']
schemas=[]
for base in [isaac/'exts/isaacsim.ros2.bridge',isaac/'exts/isaacsim.core.nodes']:
 if base.exists():
  for p in base.rglob('*.ogn'):
   if any(n in p.name for n in names):schemas.append({'path':str(p),'text':p.read_text()})
samples=[]
for rel in ['standalone_examples/api/isaacsim.ros2.bridge/rtx_lidar.py',
 'standalone_examples/api/isaacsim.ros2.bridge/camera.py']:
 p=isaac/rel
 if p.exists():samples.append({'path':str(p),'text':p.read_text()[:25000]})
tools={}
for cmd in [['bash','-c','source /opt/ros/jazzy/setup.bash && ros2 bag record --help'],
 ['bash','-c','source /opt/ros/jazzy/setup.bash && ros2 pkg prefix rosbag2_storage_mcap'],
 ['nvidia-smi','--query-gpu=name,uuid,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],
 ['ps','-eo','pid,ppid,etimes,comm,args']]:
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 out=r.stdout
 if cmd[0]=='ps':out='\n'.join(x for x in out.splitlines() if any(t in x for t in ['/root/isaacsim/kit/kit','native_capture_baseline','single06_lab','ros2 bag record']))
 tools[' '.join(cmd[:3])]={'exit':r.returncode,'stdout':out,'stderr':r.stderr[:2000]}
launch=project/'single06_lab/frozen_runtime/sensor_visualizer_v06/launcher.py'
print(json.dumps({'scene':str(scene),'scene_sha256':hashlib.sha256(scene.read_bytes()).hexdigest() if scene.exists() else None,
 'schemas':schemas,'samples':samples,'tools':tools,'launcher':launch.read_text() if launch.exists() else None,
 'kit_exists':(isaac/'kit/kit').exists(),'python_sh_exists':(isaac/'python.sh').exists()},ensure_ascii=False))
