import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004')
with (root/'reports/suite_supervisor.log').open('ab') as f:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'suite.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
print(json.dumps({'pid':p.pid}))
