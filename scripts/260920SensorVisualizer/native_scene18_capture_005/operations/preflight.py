import hashlib,json,shutil,subprocess
from pathlib import Path
base=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
pids=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):pids.append(int(p.parent.name))
 except OSError:pass
q=subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15)
print(json.dumps({'scene_sha256':hashlib.sha256(scene.read_bytes()).hexdigest(),'scene_bytes':scene.stat().st_size,'kit_pids':pids,'gpu':q.stdout,'free_gib':shutil.disk_usage('/root/gpufree-data').free/1024**3,'ros_ready':Path('/opt/ros/jazzy/setup.bash').is_file(),'new_project_exists':(base/'native_scene18_capture_005').exists()}))
