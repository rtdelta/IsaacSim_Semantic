import json
from pathlib import Path
root=Path('/root/isaacsim')
result=[]
for p in root.glob('extscache/omni.replicator.core-*/omni/replicator/core/scripts/orchestrator.py'):
    lines=p.read_text().splitlines()
    for i,l in enumerate(lines):
        if l.startswith('    async def wait_until_complete_async') or l.startswith('    def stop('):
            result.append({'path':str(p),'start':i+1,'text':'\n'.join(lines[i:i+65])})
print(json.dumps(result))
