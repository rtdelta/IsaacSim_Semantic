"""Read only: hash deployed logging sources without importing project modules."""
import hashlib
import json
from pathlib import Path

base = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07/sensor_visualizer_v07')
names = ('resources.py', 'resource_details.py', 'diagnostics.py', 'native_trace.py', 'contracts.py')
rows = []
for name in names:
    p = base / name
    rows.append({'file': name, 'exists': p.is_file(),
                 'sha256': hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None})
print(json.dumps({'intent': 'read only; project not imported', 'base': str(base), 'files': rows}))
