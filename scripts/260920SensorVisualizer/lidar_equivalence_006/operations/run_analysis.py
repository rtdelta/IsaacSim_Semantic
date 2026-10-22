import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
with (out/'analysis.log').open('w') as log:
 p=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc006',str(R/'analyze.py'),str(out)],cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'analysis_pid':p.pid,'directory':str(out)}))
