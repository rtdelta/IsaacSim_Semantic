import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
assert json.loads((out/'causal_progress.json').read_text()).get('finished')
assert not (out/'causal_retry_progress.json').exists()
with (out/'causal_retry.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(R/'causal_retry.py')],cwd=R,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({'pid':p.pid}))
