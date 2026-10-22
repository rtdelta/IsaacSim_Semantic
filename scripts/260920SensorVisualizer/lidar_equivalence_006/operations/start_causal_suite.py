import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
assert not (out/'causal_progress.json').exists()
with (out/'causal_suite.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(R/'causal_suite.py')],cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'pid':p.pid}))
