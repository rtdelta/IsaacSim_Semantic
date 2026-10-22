import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency/clock_20261014_v1')
out=[]
for condition in ('T0_B','T2_Rplus'):
    path=root/condition/'repeats/r01/continuous/phase_clock_trace.jsonl'
    if not path.exists():continue
    selected=[]
    for line in path.open():
        r=json.loads(line)['data']
        if r['phase']=='physics_post_actual' and r['physical_step'] in (40,41,42,46,47,48,100):
            selected.append({'step':r['physical_step'],'fabric_components':r['fabric_components'],'usd_matrix':r['usd_world']})
    out.append({'condition':condition,'samples':selected})
print(json.dumps(out))
