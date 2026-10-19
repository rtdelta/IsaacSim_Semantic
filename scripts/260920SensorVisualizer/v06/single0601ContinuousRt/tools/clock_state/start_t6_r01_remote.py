import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
prior=json.loads((root/'reports/clock_state_consistency/batches/clock_20261014_t5/status.json').read_text())
if prior['state']!='COMPLETE' or not all(r['measurement_qualified'] for r in prior['runs']):raise RuntimeError('Prior batch not qualified')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/coordinator.py'),'--batch',str(root/'config/clock_state/t6_r01_batch.json')],check=True)
