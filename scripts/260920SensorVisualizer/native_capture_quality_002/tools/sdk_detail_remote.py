import json
from pathlib import Path
root=Path('/root/isaacsim');result=[]
targets=['omni/replicator/core/scripts/orchestrator.py','omni/replicator/core/scripts/settings.py']
for base in (root/'exts',root/'extscache'):
 for d in base.glob('omni.replicator.core*'):
  for rel in targets:
   f=d/rel
   if not f.exists():continue
   lines=f.read_text().splitlines();idx=set()
   for i,l in enumerate(lines):
    if any(x in l for x in ('async def stop_async','async def wait_until_complete_async','def wait_until_complete','def _validate_pt_settings','def _get_pt_subframes_per_frame')):idx.update(range(max(0,i-3),min(len(lines),i+45)))
   result.append({'path':str(f),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(idx))})
print(json.dumps(result))
