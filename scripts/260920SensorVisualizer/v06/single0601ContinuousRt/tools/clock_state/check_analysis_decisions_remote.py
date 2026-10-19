import json
from pathlib import Path
parent=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency/clock_20261014_v1/T0_A/repeats/r01')
checks={}
for filename,keys in [('planned_target_metrics.json',['clock_mapping_ok','native_pose_ok','geometry_ok','event_provenance_ok','input_qualified','joint_cell']),
    ('component_delay.json',['status','best_members','position_delay_identifiable','rotation_delay_identifiable','position_lag_steps','rotation_lag_steps'])]:
    a=json.loads((parent/'analysis'/filename).read_text());b=json.loads((parent/'analysis_cpu1'/filename).read_text())
    checks[filename]={'rows':len(a),'equal':len(a)==len(b) and all(all(x[k]==y[k] for k in keys) for x,y in zip(a,b))}
report=json.loads((parent/'analysis_cpu1/consistency_check.json').read_text());report.update(per_target_decisions=checks,all_per_target_decisions_equal=all(v['equal'] for v in checks.values()))
(parent/'analysis_cpu1/consistency_check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if not report['all_per_target_decisions_equal']:raise RuntimeError('Per-target analysis decisions changed')
