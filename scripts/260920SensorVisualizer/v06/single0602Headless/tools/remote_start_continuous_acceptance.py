import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
tag='continuous_acceptance'
with (root/'reports'/(tag+'_runner.log')).open('wb') as log:
    process=subprocess.Popen(['/usr/bin/python3',str(root/'tools/native_test_runner.py'),
        'tools/continuous_acceptance_entry.py',tag],stdin=subprocess.DEVNULL,stdout=log,
        stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
print(json.dumps({'runner_pid':process.pid,'tag':tag}))
