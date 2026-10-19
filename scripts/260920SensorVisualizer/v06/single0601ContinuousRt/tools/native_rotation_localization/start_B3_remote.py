import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');suite=root/'reports/native_rotation_localization/native007_20261015_v1'
if json.loads((suite/'sequences/main_m02/status.json').read_text())['state']!='TERMINAL_WITH_BLOCKED_BRANCHES':raise RuntimeError('Main not terminal')
if not json.loads((suite/'qualification_release.json').read_text())['trigger_B3']:raise RuntimeError('B3 trigger absent')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/coordinator.py'),'--sequence',str(root/'config/native_rotation_localization/v1/extension_B3_q01_sequence.json')],check=True)
