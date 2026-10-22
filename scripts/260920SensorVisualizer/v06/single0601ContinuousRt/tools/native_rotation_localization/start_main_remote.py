import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
release=json.loads((root/'reports/native_rotation_localization/native007_20261015_v1/qualification_release.json').read_text())
if release['released_conditions']!=['A0','A1','B1','B2'] or not all(r['measurement_qualified'] for r in release['replays'] if r['condition'] in release['released_conditions']):raise RuntimeError('Final qualification release unavailable')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/coordinator.py'),'--sequence',str(root/'config/native_rotation_localization/v1/main_m02_sequence.json')],check=True)
