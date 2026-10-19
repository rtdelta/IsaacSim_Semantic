"""Read-only fingerprints for the deployed usage instructions and UI entries."""
import hashlib
import json
from pathlib import Path

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
names = ['tools/open_surround_stage.sh', 'run_in_isaac.py', 'launch_isaac.py',
         'launch_rviz.py', 'config/sensors.json', 'SURROUND_USAGE.md',
         'sensor_visualizer/session.py', 'sensor_visualizer/runtime.py',
         'sensor_visualizer/base_panel.py', 'sensor_visualizer/joint_panel.py',
         'sensor_visualizer/config.py', 'sensor_visualizer/pose_panel.py']
out = {}
for name in names:
    p = root / name
    out[name] = {'exists': p.is_file()}
    if p.is_file():
        out[name]['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        out[name]['normalized_sha256'] = hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
print(json.dumps(out))
