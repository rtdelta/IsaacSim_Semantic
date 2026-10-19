import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');suite=root/'reports/native_rotation_localization/native007_20261015_v1'
p=suite/'C1/S0/r01/cq01/warmup_semantics_analysis.json'
if not json.loads(p.read_text())['cleanup']['passed']:raise RuntimeError('C1 cleanup incomplete')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/coordinator.py'),'--sequence',str(root/'config/native_rotation_localization/v1/extension_T3_resume_q01_sequence.json')],check=True)
