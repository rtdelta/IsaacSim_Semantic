from pathlib import Path
import json
out=[]
roots=list(Path('/root/isaacsim/extscache').glob('omni.replicator.core-*'))
for root in roots:
    for path in root.rglob('*.py'):
        if 'tests' in path.parts:continue
        lines=path.read_text(errors='replace').splitlines()
        for n,line in enumerate(lines):
            if path.name=='orchestrator.py' and any(key in line for key in ('async def stop_async','def stop(', 'self._timeline.stop(', 'resetOnStop', 'resetTimeline')):
                out.append({'path':str(path),'line':n+1,'source':'\n'.join(lines[max(0,n-8):n+45])})
print(json.dumps(out))
