"""Launch the project-owned bounded lifecycle validation in the background."""
import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
with (root/'reports/capture_lifecycle.log').open('ab') as log:
    p=subprocess.Popen(['/usr/bin/python3',str(root/'tools/capture_lifecycle_runner.py')],
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'pid':p.pid,'entry':str(root/'tools/capture_lifecycle_runner.py')}))
