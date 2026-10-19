from pathlib import Path
import json
v={}
roots=[Path('/root/isaacsim/exts/isaacsim.ros2.nodes'),Path('/root/isaacsim/exts/isaacsim.core.nodes')]+list(Path('/root/isaacsim/extscache').glob('omni.replicator.core-*'))
terms=('IsaacReadSimulationTime','WriterSyncGate','ROS2PublishImage','ROS2PublishPointCloud','referenceTime','simulationTime','frameSkipCount')
for root in roots:
 for p in root.rglob('*'):
  if not p.is_file() or p.suffix not in ('.py','.ogn','.json','.cpp','.h'):continue
  if 'ogn/python' in str(p) or '/tests/' in str(p):continue
  if p.stat().st_size>180000:continue
  s=p.read_text(errors='replace');name=p.name
  if name=='orchestrator.py':
   lines=s.splitlines();v[str(p)]='\n'.join(f'{i+1}: {lines[i]}' for i in range(390,min(535,len(lines))));continue
  if name=='base_writer_node.py':v[str(p)]=s;continue
  if 'SimulationTime' in name or name=='writers.py' or name=='extension.py' and any(x in s for x in terms):
   lines=s.splitlines();hits={i for i,l in enumerate(lines) if any(t in l for t in terms)};inds=set()
   for i in hits:inds.update(range(max(0,i-8),min(len(lines),i+14)))
   v[str(p)]='\n'.join(f'{i+1}: {lines[i]}' for i in sorted(inds))[:35000]
print(json.dumps(v))
