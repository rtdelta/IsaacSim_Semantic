"""Launch a task-owned GUI capability probe after checking process ownership."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:
            args = (p/'cmdline').read_bytes()
            if b'/kit/kit' in args:
                raise RuntimeError('An Isaac process is already running; do not stop or duplicate it')
        except FileNotFoundError:
            pass
reports = root/'reports'
reports.mkdir(exist_ok=True)
log = reports/('probe_launch_' + time.strftime('%Y%m%d_%H%M%S') + '.log')
env = os.environ.copy()
env['DISPLAY'] = ':20'
env['S0601_FORCE_BARRIER']='1'
with log.open('xb') as f:
    p = subprocess.Popen(['/usr/bin/python3', '-B', str(root/'run_capture.py'), '--job', str(root/'config/mixed_pair.json'), '--barrier-probe'],
                         cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
receipt = {'pid': p.pid, 'log': str(log), 'project': str(root), 'launched_monotonic_ns': str(time.monotonic_ns()),
           'entrypoint_sha256': hashlib.sha256((root/'tools/probe_barrier.py').read_bytes()).hexdigest()}
(reports/'probe_process.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
