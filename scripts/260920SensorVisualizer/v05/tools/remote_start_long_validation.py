import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05');directory=root/'reports/native_owner'
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:raw=(p/'cmdline').read_bytes()
        except OSError:continue
        if str(root/'tools/long_validation_runner.py').encode() in raw:raise RuntimeError('Long test already running')
log=(directory/'soak_runner.log').open('ab')
p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'tools/long_validation_runner.py')],cwd=root,
    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
print(json.dumps({'started_pid':p.pid,'duration_s':1800,'groups':100}))
