import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
d=json.loads((root/'reports/issue_repro/minimal_20261016_v1/static_on/settings.json').read_text())
print(json.dumps({k:{'requested':v,'effective':d['effective'][k]} for k,v in d['requested'].items() if d['effective'][k]!=v}))
