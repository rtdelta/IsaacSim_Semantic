"""Twenty independent recordings in the same task-owned GUI, no other engine."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:
            if b'/kit/kit' in (p/'cmdline').read_bytes():
                raise RuntimeError('An Isaac process is running; this launch cannot duplicate it')
        except FileNotFoundError:
            pass
reports=root/'reports'
log=reports/('lifecycle_launch_'+time.strftime('%Y%m%d_%H%M%S')+'.log')
env=os.environ.copy()
env.update(DISPLAY=':20',S0601_FORCE_BARRIER='1',S0601_MATRIX=str(root/'config/acceptance_lifecycle.json'))
with log.open('xb') as f:
    process=subprocess.Popen(['/usr/bin/python3','-B',str(root/'run_capture.py'),'--job',str(root/'config/mixed_pair.json')],cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':process.pid,'log':str(log),'project':str(root),'launched_monotonic_ns':str(time.monotonic_ns()),
         'entrypoint_sha256':hashlib.sha256((root/'run_in_isaac.py').read_bytes()).hexdigest(),'matrix':env['S0601_MATRIX']}
(reports/'record_process.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
