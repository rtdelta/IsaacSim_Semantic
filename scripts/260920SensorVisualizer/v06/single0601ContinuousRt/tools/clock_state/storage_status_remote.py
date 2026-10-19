import json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
out=[]
for p in (root/'reports/clock_state_consistency').rglob('file_manifest.json'):
    d=json.loads(p.read_text());out.append({'path':str(p.relative_to(root)), 'files':len(d['files']), 'bytes':sum(f['bytes'] for f in d['files'])})
print(json.dumps({'disk_free_bytes':shutil.disk_usage(root).free,'completed_evidence':out}))
