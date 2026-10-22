import json,os,signal,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/unified_bag/acceptance')
result=json.loads((root/'result.json').read_text())
if not result['passed']:raise RuntimeError('Inspect failed acceptance before cleanup')
identity=json.loads((root/'process.json').read_text());pid=identity['pid'];folder=Path('/proc')/str(pid)
def state():
    if not folder.exists():return 'exited'
    fields=(folder/'stat').read_text().split()
    if fields[21]!=identity['start_ticks']:raise RuntimeError('PID identity changed')
    return fields[2]
before=state();actions=[]
if before not in ('exited','Z'):
    args=(folder/'cmdline').read_bytes()
    if b'validate_unified_runtime.py' not in args:raise RuntimeError('Not the owned acceptance instance')
    os.kill(pid,signal.SIGTERM);actions.append('SIGTERM owned completed acceptance')
    for _ in range(20):
        time.sleep(.5)
        if state() in ('exited','Z'):break
    if state() not in ('exited','Z'):
        os.kill(pid,signal.SIGKILL);actions.append('SIGKILL owned completed acceptance after grace period')
        time.sleep(1)
print(json.dumps(dict(before=before,after=state(),actions=actions,original_user_kit_exists=Path('/proc/793358').exists())))
