"""Stop only the redundant GUI test launched after a failed tool deployment."""
from pathlib import Path
import json,os,signal,time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03')
out=Path(json.loads((root/'reports/latest_headless_test.json').read_text())['directory'])
if out.name!='20261008_152432_897200_headless':raise RuntimeError('Unexpected test; no action')
record=json.loads((out/'process.json').read_text());pid=record['pid']
if '--gui' not in record['command'] or str(root/'tools/kit_acceptance.py') not in record['command']:
    raise RuntimeError('Expected only redundant task-owned GUI test')
def matching():
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]==record['identity']['start']
    except OSError:return False
if matching():
    if os.getpgid(pid)!=pid:raise RuntimeError('Unexpected process group')
    os.killpg(pid,signal.SIGTERM)
    for _ in range(20):
        if not matching():break
        time.sleep(.25)
    if matching():os.killpg(pid,signal.SIGKILL)
print(json.dumps({'stopped_redundant_test':str(out),'pid':pid,'reason':'Headless launcher tools were not deployed due to SSH handshake failure'}))
