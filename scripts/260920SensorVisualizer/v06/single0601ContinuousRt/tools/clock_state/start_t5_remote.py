import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
prior=json.loads((root/'reports/clock_state_consistency/batches/clock_20261014_branches_qualification/status.json').read_text())
if prior['state']!='COMPLETE' or not all(r['measurement_qualified'] for r in prior['runs']):raise RuntimeError('Prior batch not qualified')
gate=json.loads((root/'reports/clock_state_consistency/clock_20261014_v2/v2_provenance_gate_verification.json').read_text())
if not gate['all_qualified']:raise RuntimeError('Stricter source-provenance gate not qualified')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/coordinator.py'),'--batch',str(root/'config/clock_state/t5_batch.json')],check=True)
