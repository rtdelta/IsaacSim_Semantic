"""Historical failure stays intact; reanalysis must reject full-run qualification."""
import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
parent=root/'reports/clock_state_consistency/clock_20261014_v1/T4_B120_3_qualification/repeats/r01'
env=os.environ.copy()
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[key]='1'
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/analyze.py'),str(parent),'analysis_lifecycle_gate'],env=env,check=True,stdout=subprocess.DEVNULL,timeout=120)
before=json.loads((parent/'analysis/summary.json').read_text());after=json.loads((parent/'analysis_lifecycle_gate/summary.json').read_text())
same={name:json.loads((parent/'analysis'/name).read_text())==json.loads((parent/'analysis_lifecycle_gate'/name).read_text()) for name in ('planned_target_metrics.json','component_delay.json','clock_metrics.json')}
result={'measurement_qualified':after['measurement_qualified'],'lifecycle_qualified':after['lifecycle_qualified'],'run_qualified':after['run_qualified'],'same_measurements':same,'original_analysis_preserved':True}
if not after['measurement_qualified'] or after['lifecycle_qualified'] or after['run_qualified'] or not all(same.values()):raise RuntimeError('Lifecycle gate regression mismatch')
(root/'reports/clock_state_consistency/lifecycle_gate_regression.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
