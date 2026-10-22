import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
with (root/'reports/gui_shutdown_runner.log').open('ab') as log:
    process=subprocess.Popen(['/usr/bin/python3',str(root/'tools/gui_shutdown_runner.py')],
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'pid':process.pid,'entry':'gui_shutdown_runner.py'}))
