import json
import os
from pathlib import Path
import subprocess

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
report=root/'reports/tilt_terrain';report.mkdir(parents=True,exist_ok=True)
pidfile=report/'cloud_diagnostic_process.json'
if pidfile.exists():
    previous=json.loads(pidfile.read_text())
    p=Path('/proc')/str(previous['pid'])
    if p.exists() and (p/'stat').read_text().split()[21]==previous['start_ticks']:
        raise RuntimeError('The previous validation process is still present; inspect it before retry')
env=dict(os.environ);env['DISPLAY']=':20';env['PYTHONDONTWRITEBYTECODE']='1'
with (report/'cloud_diagnostic_kit.log').open('wb') as log:
    child=subprocess.Popen(['/usr/bin/python3',str(root/'launch_isaac.py'),
        '--/app/extensions/registryEnabled=false','--exec',str(root/'tools/diagnose_terrain_clouds.py')],
        cwd=str(root),env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
    identity={'pid':child.pid,'start_ticks':(Path('/proc')/str(child.pid)/'stat').read_text().split()[21],
              'purpose':'isolated tilt/terrain validation','log':str(report/'cloud_diagnostic_kit.log')}
    pidfile.write_text(json.dumps(identity,indent=2))
print(json.dumps(identity))
