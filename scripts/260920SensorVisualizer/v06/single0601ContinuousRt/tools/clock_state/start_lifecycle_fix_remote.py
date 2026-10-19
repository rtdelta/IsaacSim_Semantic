import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
prior=json.loads((root/'reports/clock_state_consistency/batches/clock_20261014_t6_r03/status.json').read_text())
if prior['state']!='COMPLETE':raise RuntimeError('Main rounds not complete')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/coordinator.py'),'--batch',str(root/'config/clock_state/lifecycle_fix_batch.json')],check=True)
