import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency')
files=[]
for p in root.rglob('*'):
    rel=p.relative_to(root)
    if not p.is_file() or any(s in rel.parts for s in ('payloads','trace_samples')) or p.suffix not in ('.json','.jsonl') or p.name in ('sensor_registry.json','gmo_headers.json'):continue
    files.append((p.stat().st_size,rel.as_posix()))
print(json.dumps({'files':len(files),'total_bytes':sum(n for n,_ in files),'largest':sorted(files,reverse=True)[:5]}))
