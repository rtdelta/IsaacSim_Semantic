import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
with (root/'reports/continuous_capture_runner.log').open('wb') as log:
    process=subprocess.Popen(['/usr/bin/python3',str(root/'tools/continuous_capture_runner.py'),'--native-only'],
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
print(json.dumps({'runner_pid':process.pid}))
