import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
rows=[]
for case in json.loads((out/'progress.json').read_text())['completed']:
    if case['exit_code']:continue
    for p in sorted((Path(case['directory'])/'capture/formal_clouds/000').glob('*.json')):
        r=json.loads(p.read_text());rows.append({k:r[k] for k in ('sensor','points','stamp_ns','sha256_xyz','info_keys')}|{'family':case['family'],'round':case['round']})
print(json.dumps(rows,indent=2))
