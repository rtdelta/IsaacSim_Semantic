import json,os,runpy,signal,sys,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
owner=json.loads((root/'reports/native_owner/owner.json').read_text())
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:raw=(p/'cmdline').read_bytes()
        except OSError:continue
        if str(root/'tools/long_validation_runner.py').encode() in raw:os.kill(int(p.name),signal.SIGTERM)
request(owner['socket'],{'action':'pause'})
if request(owner['socket'],{'action':'status'}).get('recording'):
    request(owner['socket'],{'action':'record_stop'})
    end=time.monotonic()+5
    while request(owner['socket'],{'action':'status'}).get('recording') and time.monotonic()<end:time.sleep(.05)
for name in ('soak_status.json','soak_resources.jsonl'):
    p=root/'reports/native_owner'/name
    if p.exists():p.rename(p.with_name(p.name+'.prior_'+str(time.time_ns())))
runpy.run_path(str(root/'tools/remote_start_long_validation.py'),run_name='__main__')
