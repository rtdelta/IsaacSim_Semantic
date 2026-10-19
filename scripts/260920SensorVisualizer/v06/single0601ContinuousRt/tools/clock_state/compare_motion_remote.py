import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency/clock_20261014_v1')
out={'schema_version':1,'comparisons':[]}
def read(condition,repeat):
    p=root/condition/'repeats'/repeat/'analysis'
    if not (p/'summary.json').exists():return None
    return {'summary':json.loads((p/'summary.json').read_text()),'metrics':json.loads((p/'planned_target_metrics.json').read_text()),
        'components':json.loads((p/'component_delay.json').read_text())}
for repeat in ('r01','r02','r03'):
    for a,b in [('T2_Rplus','T2_Rminus'),('T0_B','T2_Rplus')]:
        x,y=read(a,repeat),read(b,repeat)
        if not x or not y:continue
        old={r['target_index']:r for r in x['components']};new={r['target_index']:r for r in y['components']}
        differences=[i for i in range(100) if i not in old or i not in new or old[i]['rotation_lag_steps']!=new[i]['rotation_lag_steps']]
        native=[i for i,(p,q) in enumerate(zip(x['metrics'],y['metrics'])) if p['native_pose_ok']!=q['native_pose_ok']]
        out['comparisons'].append({'conditions':[a,b],'repeat':repeat,'rotation_lag_different_targets':differences,
            'native_pose_class_different_targets':native,'both_measurement_qualified':x['summary']['measurement_qualified'] and y['summary']['measurement_qualified']})
(root/'motion_component_comparison.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
