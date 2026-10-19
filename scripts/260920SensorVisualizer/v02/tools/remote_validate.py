from pathlib import Path
import json
import os
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v02')
sessions=[p.parent for p in sorted(output.glob('20*/session.json')) if json.loads(p.read_text())['state']=='finished']
if not sessions: raise RuntimeError('No finished v02 session')
env=os.environ.copy()
for key in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH','CONDA_PREFIX','VIRTUAL_ENV'): env.pop(key,None)
result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',
 'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2" --export-images',
 'sv02-validate',str(root/'tools/validate_capture.py'),str(sessions[-1])],env=env,capture_output=True,text=True,timeout=120)
print(json.dumps({'session':str(sessions[-1]),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}))
