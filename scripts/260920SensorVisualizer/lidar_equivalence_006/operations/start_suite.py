import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
latest=json.loads((R/'reports/latest.json').read_text());out=Path(latest['directory'])
if (out/'progress.json').exists():raise RuntimeError('Suite already exists; inspect before retry')
with (out/'suite.log').open('xb') as log:
    p=subprocess.Popen(['/usr/bin/python3','-u',str(R/'suite.py')],cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
latest.update(phase='paired_static',suite_pid=p.pid);(R/'reports/latest.json').write_text(json.dumps(latest,indent=2));print(json.dumps(latest))
