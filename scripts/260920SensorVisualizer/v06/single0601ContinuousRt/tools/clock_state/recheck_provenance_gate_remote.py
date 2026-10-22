"""Recompute short qualifications into new outputs after a stricter source gate."""
import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
base=root/'reports/clock_state_consistency/clock_20261014_v2';env=os.environ.copy()
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[key]='1'
status=json.loads((root/'reports/clock_state_consistency/batches/clock_20261014_branches_qualification/status.json').read_text())
if status['state']!='COMPLETE':raise RuntimeError('Qualification batch still running or failed')
reports=[]
for entry in status['runs']:
    parent=Path(entry['directory']);output=parent/'analysis_provenance_gate'
    if output.exists():raise RuntimeError('Refuse reanalysis overwrite')
    r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/analyze.py'),str(parent),output.name],
        env=env,capture_output=True,text=True,timeout=90)
    if r.returncode:raise RuntimeError(r.stdout[-2000:]+r.stderr[-2000:])
    before=json.loads((parent/'analysis/summary.json').read_text());after=json.loads((output/'summary.json').read_text())
    same_metrics=json.loads((parent/'analysis/planned_target_metrics.json').read_text())==json.loads((output/'planned_target_metrics.json').read_text())
    same_components=json.loads((parent/'analysis/component_delay.json').read_text())==json.loads((output/'component_delay.json').read_text())
    reports.append({'condition':before['spec']['condition'],'before_qualified':before['measurement_qualified'],
        'after_qualified':after['measurement_qualified'],'target_provenance_qualified':after['target_provenance_qualified'],
        'per_target_metrics_equal':same_metrics,'candidate_decisions_equal':same_components})
    if not all((after['measurement_qualified'],same_metrics,same_components)):raise RuntimeError('Reanalysis changed qualification or target decisions')
result={'schema_version':1,'conditions':reports,'all_qualified':len(reports)==6 and all(r['after_qualified'] for r in reports)}
(base/'v2_provenance_gate_verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
