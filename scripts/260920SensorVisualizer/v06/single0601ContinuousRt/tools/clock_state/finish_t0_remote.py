import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
base=root/'reports/clock_state_consistency/clock_20261014_v1'
comparisons=[];summaries=[]
for repeat in ('r01','r02','r03'):
    a=base/'T0_A/repeats'/repeat;b=base/'T0_B/repeats'/repeat
    r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/compare_observer.py'),str(a),str(b),str(base/('T0_observer_'+repeat+'.json'))],capture_output=True,text=True,check=True)
    comparisons.append(json.loads(r.stdout))
    for p in (a,b):
        s=json.loads((p/'analysis/summary.json').read_text());s.pop('spec',None);summaries.append({'directory':str(p),'summary':s})
report={'schema_version':1,'comparisons':comparisons,'runs':summaries,
    'all_measurement_qualified':all(r['summary']['measurement_qualified'] for r in summaries),
    'all_failure_indices_equal':all(not c['target_failure_class_different_indices'] for c in comparisons),
    'planned_sensor_targets_per_side':600,'formal_continuous_acceptance':False,
    'repeat_unit':'independent paired Kit initialization, n=3 per observer condition; frames are not independent repetitions'}
(base/'T0_observer_summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
