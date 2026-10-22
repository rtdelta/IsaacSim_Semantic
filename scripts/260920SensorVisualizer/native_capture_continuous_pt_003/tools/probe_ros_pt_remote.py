import json
from pathlib import Path
v={}
roots=list(Path('/root/isaacsim/exts').glob('isaacsim.ros2*'))+list(Path('/root/isaacsim/extscache').glob('omni.replicator.core-*'))
for root in roots:
 for p in root.rglob('*.py'):
  if p.name in ('OgnROS2CameraHelper.py','OgnROS2CameraInfoHelper.py','OgnROS2RtxLidarHelper.py','writers.py','base_writer_node.py','orchestrator.py'):
   s=p.read_text(errors='replace').splitlines();terms=['SimulationTime','simulationTime','timeStamp','resetSimulationTime','syncGate','SyncGate','sim_time','_sim_time','_get_pt_subframes','_num_captured_frames','lastFrameTime','fabricFrameTime']
   hits={i for i,l in enumerate(s) if any(t in l for t in terms)};lines=set()
   for i in hits:lines.update(range(max(0,i-6),min(len(s),i+9)))
   v[str(p)]='\n'.join(f'{i+1}: {s[i]}' for i in sorted(lines))[:18000]
for root in Path('/root/isaacsim/exts').glob('isaacsim.core*'):
 for p in root.rglob('*Read*Simulation*Time*'):
  if p.suffix in ('.ogn','.py'):v[str(p)]=p.read_text(errors='replace')[:16000]
print(json.dumps(v))
