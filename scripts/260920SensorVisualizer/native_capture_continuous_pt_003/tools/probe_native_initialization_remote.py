from pathlib import Path
import json
v={}
for root in [Path('/root/isaacsim/exts/isaacsim.core.nodes'),Path('/root/isaacsim/exts/isaacsim.ros2.bridge'),*Path('/root/isaacsim/extscache').glob('omni.replicator.core-*')]:
 for p in root.rglob('*.py'):
  if p.name=='base_writer_node.py':v[str(p)]=p.read_text();continue
  if p.name=='orchestrator.py':
   lines=p.read_text().splitlines();terms=('preview_async','initialize_async','capture_on_play','_resume_play','sim_times_to_write','def set_sim_time','def start_async')
   inds=set()
   for i,l in enumerate(lines):
    if any(t in l for t in terms):inds.update(range(max(0,i-3),min(len(lines),i+12)))
   v[str(p)]='\n'.join(f'{i+1}:{lines[i]}' for i in sorted(inds))
  elif p.name=='extension.py' and '/ros2/' in str(p):
   lines=p.read_text().splitlines();terms=('IsaacReadSimulationTime','ROS2PublishImage','ROS2PublishPointCloud','IsaacSimulationGate','execIn','inputs:timeStamp');inds=set()
   for i,l in enumerate(lines):
    if any(t in l for t in terms):inds.update(range(max(0,i-8),min(len(lines),i+20)))
   v[str(p)]='\n'.join(f'{i+1}:{lines[i]}' for i in sorted(inds))[:25000]
print(json.dumps(v))
