import json
from pathlib import Path
roots=[Path('/root/isaacsim/exts/isaacsim.ros2.nodes'),Path('/root/isaacsim/exts/isaacsim.core.nodes')]
rows=[]
keys=('class OgnROS2CameraInfoHelper','class BaseWriterNode')
for root in roots:
 for p in root.rglob('*.py'):
  if '/tests/' in str(p) or '/ogn/python/' in str(p):continue
  lines=p.read_text(errors='replace').splitlines();idx=set()
  for i,l in enumerate(lines):
   if any(k in l for k in keys):idx.update(range(max(0,i-5),min(len(lines),i+210)))
  if idx:rows.append({'path':str(p),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(idx))})
for root in (Path('/root/isaacsim/exts'),Path('/root/isaacsim/extscache')):
 for d in root.glob('omni.replicator.core*'):
  for rel in ('omni/replicator/core/scripts/writers.py',):
   p=d/rel
   if not p.exists():continue
   lines=p.read_text(errors='replace').splitlines();idx=set()
   for i,l in enumerate(lines):
    if 'class NodeWriter' in l:idx.update(range(max(0,i-3),min(len(lines),i+240)))
   rows.append({'path':str(p),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(idx))})
print(json.dumps(rows))
