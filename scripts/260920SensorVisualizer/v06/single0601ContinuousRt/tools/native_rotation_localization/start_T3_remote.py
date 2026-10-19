import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');suite=root/'reports/native_rotation_localization/native007_20261015_v1'
if json.loads((suite/'sequences/extension_speed_m01/status.json').read_text())['state']!='COMPLETE':raise RuntimeError('Speed comparison not complete')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/coordinator.py'),'--sequence',str(root/'config/native_rotation_localization/v1/extension_T3_q01_sequence.json')],check=True)
