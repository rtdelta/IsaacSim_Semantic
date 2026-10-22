"""Decode owned acceptance tasks with the common strict data validator."""
import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');results=[]
allowed=('offline_task.json','live_latest_task.json','live_complete_task.json','stop_task.json','soak_task.json')
tracks=os.environ.get('SV06_VALIDATE_TRACKS',','.join(allowed)).split(',')
assert all(name in allowed for name in tracks)
for filename in tracks:
    track=root/'reports/native_owner'/filename
    if not track.exists():continue
    info=json.loads(track.read_text());status=json.loads((Path(info['directory'])/'status.json').read_text())
    assert status['state']=='finished',status
    session=Path(status['session']);env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
    p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -u "$@"','sv06-validate',str(root/'tools/validate_capture_data.py'),str(session)],env=env,capture_output=True,text=True,timeout=180)
    if p.returncode:raise RuntimeError(p.stdout[-1000:]+p.stderr[-4000:])
    value=json.loads(p.stdout.split('VALIDATION_JSON=')[-1]);value['mode']=info['mode'];results.append(value)
    label='stop_boundary' if filename=='stop_task.json' else ('soak_100' if filename=='soak_task.json' else info['mode'])
    (root/'reports/native_owner'/('validation_'+label+'.json')).write_text(json.dumps(value,indent=2))
(root/'reports/native_acceptance_validation.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
