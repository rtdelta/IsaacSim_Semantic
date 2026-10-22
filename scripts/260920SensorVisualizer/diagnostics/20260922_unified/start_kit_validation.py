import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
out=root/'reports/unified_bag/acceptance';out.mkdir(parents=True,exist_ok=True)
pidfile=out/'process.json'
if pidfile.exists():
    row=json.loads(pidfile.read_text());p=Path('/proc')/str(row['pid'])
    if p.exists() and (p/'stat').read_text().split()[21]==row['start_ticks']:raise RuntimeError('Previous owned validation still exists')
env=dict(os.environ);env['DISPLAY']=':20';env['PYTHONDONTWRITEBYTECODE']='1'
with (out/'kit.log').open('wb') as log:
    child=subprocess.Popen(['/usr/bin/python3',str(root/'launch_isaac.py'),
        '--/app/extensions/registryEnabled=false','--exec',str(root/'tools/validate_unified_runtime.py')],
        cwd=str(root),env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
row=dict(pid=child.pid,start_ticks=(Path('/proc')/str(child.pid)/'stat').read_text().split()[21],purpose='owned unified MCAP acceptance ROS domain 147')
pidfile.write_text(json.dumps(row,indent=2));print(json.dumps(row))
