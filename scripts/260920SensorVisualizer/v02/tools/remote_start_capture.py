from pathlib import Path
import json
import os
import subprocess
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
reports=root/'reports'; reports.mkdir(exist_ok=True)
record=reports/'capture_process.json'
if record.exists():
    old=json.loads(record.read_text()); p=Path('/proc')/str(old['pid'])/'cmdline'
    if p.exists() and 'kit_entry.py' in p.read_bytes().decode(errors='replace'):
        raise RuntimeError('Previous v02 capture still running')
logpath=reports/f'capture_{time.time_ns()}.log'
with logpath.open('ab') as log:
    process=subprocess.Popen(['/usr/bin/python3',str(root/'run_capture.py'),'--job',str(root/'config/smoke.json')],
        cwd=str(root),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
row={'pid':process.pid,'log':str(logpath)}
record.write_text(json.dumps(row,indent=2)+'\n')
print(json.dumps(row))
