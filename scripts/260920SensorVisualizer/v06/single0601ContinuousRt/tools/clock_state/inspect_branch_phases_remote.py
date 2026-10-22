import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency/clock_20261014_v2')
out={}
for condition in ('T5_PRE_qualification','T5_POST_qualification'):
    p=root/condition/'repeats/r01/analysis/phase_summary.json'
    if not p.exists():continue
    data=json.loads(p.read_text())
    out[condition]={'stages':{name:{k:s[k] for k in ('count','USD_Fabric_translation_m','USD_Fabric_rotation_rad','external_minus_physics_ns')}
        for name,s in data['stages'].items()},'phase_order_patterns':data['observed_phase_order_patterns']}
print(json.dumps(out))
