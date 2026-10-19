import hashlib,json,shutil,subprocess
from pathlib import Path
base=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
processes=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):processes.append(int(p.parent.name))
 except OSError:pass
q=subprocess.run(['nvidia-smi','--query-gpu=name,uuid,utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
disk=shutil.disk_usage('/root/gpufree-data')
v={'scene_sha256':hashlib.sha256(scene.read_bytes()).hexdigest(),'existing_kit_pids':processes,'gpu':q.stdout.strip(),'free_gib':disk.free/1024**3,'entries':{name:(base/name).exists() for name in ('single06_lab','native_capture_baseline','native_capture_quality_002','native_capture_continuous_pt_003')},'ros':Path('/opt/ros/jazzy/setup.bash').is_file()}
print(json.dumps(v))
