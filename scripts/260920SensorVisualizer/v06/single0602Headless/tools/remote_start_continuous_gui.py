import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
last=json.loads((root/'reports/continuous_acceptance_process.json').read_text())
assert last['state']=='exited' and last['exit_code']==0,last
tag='continuous_gui'
with (root/'reports'/(tag+'_runner.log')).open('wb') as log:
    process=subprocess.Popen(['/usr/bin/python3',str(root/'tools/native_test_runner.py'),
        'tools/continuous_acceptance_entry.py',tag,'--gui'],stdin=subprocess.DEVNULL,
        stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
print(json.dumps({'runner_pid':process.pid,'tag':tag}))
