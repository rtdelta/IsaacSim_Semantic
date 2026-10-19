"""Launch only this project's independent native acceptance process."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
(root/'reports').mkdir(exist_ok=True)
sys.path.insert(0,str(root))
from run_capture import launch_spec
record=root/'reports/acceptance_process.json'
if record.exists():
    previous=json.loads(record.read_text())
    p=Path('/proc',str(previous['pid']),'cmdline')
    if p.exists() and str(root/'tools/isaac_acceptance_entry.py').encode() in p.read_bytes():
        raise RuntimeError('This project acceptance process is already active')
command,env,cwd=launch_spec(root/'config/interactive.json',False,root/'tools/isaac_acceptance_entry.py')
with (root/'reports/isaac_acceptance.log').open('ab') as log:
    process=subprocess.Popen(command,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
info={'pid':process.pid,'entry':str(root/'tools/isaac_acceptance_entry.py')}
record.write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(dict(info,state='started',display_sockets=[p.name for p in Path('/tmp/.X11-unix').glob('X*')],xdotool_available=Path('/usr/bin/xdotool').exists())))
