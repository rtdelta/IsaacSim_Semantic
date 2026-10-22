import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
with (root/'reports/continuous_probe_runner.log').open('wb') as log:
    p=subprocess.Popen(['/usr/bin/python3',str(root/'tools/native_test_runner.py'),
        'tools/continuous_probe_entry.py','continuous_probe'],stdin=subprocess.DEVNULL,
        stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
print(json.dumps({'runner_pid':p.pid}))
