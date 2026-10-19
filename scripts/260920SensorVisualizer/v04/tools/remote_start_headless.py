"""Audited remote launcher for the actual headless CLI, not the UI harness."""
from pathlib import Path
from datetime import datetime
import json,os,subprocess
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        args=p.read_bytes().split(b'\0')
        if args and (args[0].endswith(b'/kit/kit') or any(b'record_worker.py' in a or b'supervise_v04.py' in a for a in args)):
            raise RuntimeError('Existing task/application PID '+p.parent.name+'; test not started')
    except OSError:pass
out=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v04/tests')/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_headless')
out.mkdir(parents=True,exist_ok=False)
env=os.environ.copy();env.update(SV04_TEST_OUT=str(out),SV04_TEST_HEADLESS='1')
with (out/'supervisor.log').open('wb') as log:
    child=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(ROOT/'tools/supervise_v04.py')],cwd=ROOT,env=env,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(ROOT/'reports').mkdir(exist_ok=True)
(ROOT/'reports/latest_headless_test.json').write_text(json.dumps({'directory':str(out),'supervisor_pid':child.pid}))
print(json.dumps({'directory':str(out),'supervisor_pid':child.pid}))
