import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005')
latest=root/'reports/latest.json';info=json.loads(latest.read_text());base=Path(info['directory'])
result=json.loads((base/'smoke/capture/result.json').read_text())
assert result['state']=='completed', 'Smoke did not complete validation'
assert result['group_validation']['ok'], 'Smoke group validation failed'
assert not (base/'production/capture').exists(), 'Production output already exists'
with (base/'production_supervisor.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'run.py'),'--config',str(base/'production/job.json'),'--output',str(base/'production/capture')],cwd=root,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
info.update(phase='production',production_pid=p.pid,production_started_utc_ns=time.time_ns());latest.write_text(json.dumps(info,indent=2));print(json.dumps(info))
