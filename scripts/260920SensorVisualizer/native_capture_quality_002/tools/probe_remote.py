"""Scoped read-only identity-independent environment and installed SDK evidence."""
import json,hashlib,subprocess
from pathlib import Path
root=Path('/root/isaacsim');p=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
proc=[]
for f in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=f.read_bytes().replace(b'\0',b' ').decode(errors='replace')
  if any(x in args for x in ['/kit/kit','native_capture_quality_002','native_capture_baseline/run.py','ros2 bag record']):proc.append({'pid':int(f.parent.name),'args':args[:500]})
 except OSError:pass
files=[]
for base in [root/'exts/isaacsim.core.nodes',root/'exts/isaacsim.ros2.nodes']:
 for f in base.rglob('*'):
  if f.is_file() and any(x in f.name for x in ['SimulationGate','ROS2RtxLidarHelper','ROS2CameraHelper']):
   if f.suffix in ('.py','.ogn'):files.append({'path':str(f),'text':f.read_text()[:28000]})
rep=[]
for base in [root/'exts',root/'extscache']:
 for d in base.glob('omni.replicator.core*'):
  for name in ['omni/replicator/core/scripts/settings.py','omni/replicator/core/scripts/orchestrator.py']:
   f=d/name
   if f.exists():
    t=f.read_text();lines=t.splitlines();picked=set()
    for i,l in enumerate(lines):
     if any(x in l for x in ['set_render_pathtraced','pathtracing/','reset_renderer','pause_timeline','rt_subframes']):picked.update(range(max(0,i-3),min(len(lines),i+8)))
    rep.append({'path':str(f),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(picked))[:22000]})
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
r=subprocess.run(['nvidia-smi','--query-gpu=name,uuid,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=15)
print(json.dumps({'processes':proc,'gpu':r.stdout,'gpu_exit':r.returncode,'scene_hash':hashlib.sha256(scene.read_bytes()).hexdigest(),'sources':files,'replicator':rep,'free_disk':subprocess.run(['df','-h','/root/gpufree-data'],capture_output=True,text=True).stdout},ensure_ascii=False))
