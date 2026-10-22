import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
for proc in Path('/proc').iterdir():
    if proc.name.isdigit():
        try:raw=(proc/'cmdline').read_bytes()
        except OSError:continue
        if b'/kit/kit' in raw or str(root/'tools/acceptance_suite.py').encode() in raw:
            raise RuntimeError('Preserve active Kit/task; wait before acceptance')
directory=root/'reports/native_owner';directory.mkdir(parents=True,exist_ok=True)
assert not (directory/'native_keyboard_fix.json').exists(),'Archive previous acceptance before retry'
logpath=directory/('acceptance_'+str(time.time_ns())+'.log')
with logpath.open('xb') as log:
    p=subprocess.Popen(['/usr/bin/python3','-B',str(root/'tools/acceptance_suite.py')],cwd=root,stdin=subprocess.DEVNULL,
        stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
row={'pid':p.pid,'log':str(logpath)}
(directory/'acceptance_process.json').write_text(json.dumps(row));print(json.dumps(row))
