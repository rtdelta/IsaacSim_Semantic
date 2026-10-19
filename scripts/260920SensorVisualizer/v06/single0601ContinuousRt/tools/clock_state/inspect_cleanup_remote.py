import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency')
out=[]
for p in sorted(root.glob('clock_20261014_v*/**/*_terminal.json')):
    d=json.loads(p.read_text());c=d.get('cleanup',{})
    if c.get('passed') is not True:out.append({'path':str(p.relative_to(root)),'terminal_status':d.get('status'),'cleanup':c})
print(json.dumps(out))
