import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
p=out/'geometry_analysis/summary.json'
if p.exists():
 d=json.loads(p.read_text());print(json.dumps(d,indent=2))
else:
 p=out/'geometry_analysis.log';print(p.read_text()[-6000:] if p.exists() else 'no log')
