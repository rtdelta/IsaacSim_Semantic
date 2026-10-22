from pathlib import Path
import json
import subprocess
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
logpath=root/f'reports/quality_{time.time_ns()}.log'
with logpath.open('ab') as log:
    p=subprocess.Popen(['/usr/bin/python3',str(root/'run_capture.py'),'--diagnostic','quality'],cwd=root,
        stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
row={'pid':p.pid,'log':str(logpath)}
(root/'reports/quality_process.json').write_text(json.dumps(row)); print(json.dumps(row))
