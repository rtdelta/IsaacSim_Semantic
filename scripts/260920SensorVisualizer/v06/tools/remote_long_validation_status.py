import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
p=root/'reports/native_owner/soak_status.json'
print(p.read_text() if p.exists() else json.dumps({'state':'not_started'}))
