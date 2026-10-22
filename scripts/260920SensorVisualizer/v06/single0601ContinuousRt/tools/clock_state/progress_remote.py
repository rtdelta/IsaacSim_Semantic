"""Compact read-only progress for the bounded diagnostic batches."""
import json,shutil,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency')
out={'batches':[],'running_cases':[],'recent_completed':[]}
for p in sorted((root/'batches').glob('*/status.json')):
    d=json.loads(p.read_text());out['batches'].append({k:d.get(k) for k in ('batch_id','state','pid','active_spec','failure')})
    out['batches'][-1].update(completed=len(d.get('runs',[])),planned=len(d.get('planned_order',[])))
summaries=[]
for p in root.glob('*/**/coordinator_status.json'):
    d=json.loads(p.read_text())
    if d['state']!='COMPLETE':
        item=dict(path=str(p.parent.relative_to(root)),**d)
        checkpoint=p.parent/'frozen_room/phase_checkpoint.json'
        if checkpoint.exists():
            try:item['frozen_progress']=json.loads(checkpoint.read_text())
            except ValueError:item['frozen_progress']={'state':'checkpoint write in progress'}
        out['running_cases'].append(item)
for p in root.glob('*/**/analysis/summary.json'):summaries.append((p.stat().st_mtime,p))
for _,p in sorted(summaries,reverse=True)[:4]:
    d=json.loads(p.read_text());out['recent_completed'].append(dict(path=str(p.parent.parent.relative_to(root)),**{k:d.get(k) for k in (
        'measurement_qualified','planned_sensor_targets','native_pose_failed','geometry_failed','geometry_plane_failed','C_max_abs_yaw_rad','best_candidate_group_counts')}))
out['free_bytes']=shutil.disk_usage(root).free
out['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip()
print(json.dumps(out))
