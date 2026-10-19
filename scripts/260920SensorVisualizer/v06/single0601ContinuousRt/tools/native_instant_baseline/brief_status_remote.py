import json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
order=json.loads((root/'config/native_instant_baseline/run_order.json').read_text())
out={'free_bytes':shutil.disk_usage(root).free,'batches':[],'recent_runs':[]}
sequence=root/'reports/native_instant_baseline'/order['experiment_id']/'sequence_status.json'
if sequence.exists():out['sequence']=json.loads(sequence.read_text())
for bid in order['batches']:
    p=root/'reports/native_instant_baseline/batches'/bid/'status.json'
    if p.exists():
        b=json.loads(p.read_text());out['batches'].append({k:b[k] for k in ('batch_id','pid','state','planned','active_spec','failure') if k in b}|{'finished_runs':len(b['runs'])})
for p in sorted((root/'reports/native_instant_baseline'/order['experiment_id']).glob('**/analysis/summary.json'),key=lambda p:p.stat().st_mtime)[-4:]:
    s=json.loads(p.read_text());out['recent_runs'].append({'path':str(p),**{k:s[k] for k in ('measurement_qualified','cleanup_ok','diagnostic_pass','native_pose_failed','geometry_absolute_failed','geometry_increment_failed','candidate_counts')}})
print(json.dumps(out))
