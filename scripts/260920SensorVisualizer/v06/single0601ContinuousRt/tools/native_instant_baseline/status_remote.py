import json,shutil,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_instant_baseline')
out={'free_bytes':shutil.disk_usage(root).free,'probe_results':[],'batches':[],'recent_runs':[]}
for p in sorted(root.glob('effective_*/probe_result.json')):out['probe_results'].append({'path':str(p),'result':json.loads(p.read_text())})
for p in sorted(root.glob('batches/*/status.json')):out['batches'].append(json.loads(p.read_text()))
for p in sorted(root.glob('**/coordinator_status.json'),key=lambda p:p.stat().st_mtime)[-6:]:out['recent_runs'].append({'path':str(p),'status':json.loads(p.read_text())})
print(json.dumps(out))
