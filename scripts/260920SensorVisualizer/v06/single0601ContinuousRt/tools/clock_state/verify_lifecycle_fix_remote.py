"""Read native regression reports and compare immutable capture inputs/outcomes."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency')
state=json.loads((root/'batches/clock_20261014_lifecycle_fix/status.json').read_text())
if state['state']!='COMPLETE':raise RuntimeError('Lifecycle regression is not complete')
out={'schema_version':1,'runs':[],'historical_failed_runs_retained':True,'formal_continuous_acceptance':False}
for hz,old in [(120,'clock_20261014_v1/T4_B120_3_qualification'),(60,'clock_20261014_v2/T5_PRE_qualification')]:
 a=root/old/'repeats/r01';b=root/('clock_20261014_v3_lifecycle/lifecycle_'+str(hz))/'repeats/r01'
 def read(p):return json.loads(p.read_text())
 def states(p):return {s['physical_step']:s['sensor_world_matrices_usd'] for s in (json.loads(line)['data'] for line in (p/'continuous/actual_states.jsonl').read_text().splitlines())}
 def classes(p):return [(r['clock_mapping_ok'],r['native_pose_ok'],r['geometry_ok']) for r in read(p/'analysis/planned_target_metrics.json')]
 def candidates(p):return [(r['status'],r['best_members']) for r in read(p/'analysis/component_delay.json')]
 summary=read(b/'analysis/summary.json')
 row={'hz':hz,'baseline':str(a),'regression':str(b),'same_all_actual_matrices':states(a)==states(b),'same_target_classifications':classes(a)==classes(b),
   'same_candidate_classifications':candidates(a)==candidates(b),'run_qualified':summary['run_qualified'],'cleanup':{side:read(b/name)['cleanup'] for side,name in [('C','continuous_terminal.json'),('F','frozen_terminal.json')]}}
 if not row['run_qualified'] or not all(row[k] for k in ('same_all_actual_matrices','same_target_classifications','same_candidate_classifications')):raise RuntimeError('Lifecycle regression mismatch '+str(hz))
 out['runs'].append(row)
(root/'lifecycle_fix_verification.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
