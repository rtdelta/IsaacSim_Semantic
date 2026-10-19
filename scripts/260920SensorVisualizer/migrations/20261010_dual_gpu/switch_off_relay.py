"""Stop only this task's slow archive receiver after direct transfer is proven."""
import json,os,signal
from pathlib import Path
work=Path('/root/gpufree-data/.migration_sensor_20261010_dual')
state=json.loads((work/'direct_status.json').read_text())
print(json.dumps({'direct_status':state}),flush=True)
assert state['phase'] in {'transferring','validating','finished'} and state.get('bytes',9*1024*1024)>=8*1024*1024,'Direct data route is not yet proven'
found=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:raw=(p/'cmdline').read_bytes();stamp=(p/'stat').read_text().split()[21]
    except OSError:continue
    if str(work).encode() in raw and b"p=w/'assets_and_code.tar.gz.part'" in raw and b'sys.stdin.buffer.read(1048576)' in raw:
        found.append((int(p.name),stamp))
assert len(found)<=1,'Multiple receiver matches; refuse broad termination'
stopped=[]
for pid,stamp in found:
    p=Path('/proc')/str(pid)
    if p.exists() and (p/'stat').read_text().split()[21]==stamp:
        os.kill(pid,signal.SIGTERM);stopped.append(pid)
print(json.dumps({'stopped_task_relay_receiver_pids':stopped}))
