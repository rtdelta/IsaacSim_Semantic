import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
path=root/'reports/native_validation_status.json'
status=json.loads(path.read_text()) if path.exists() else {'state':'not_started'}
compact={k:v for k,v in status.items() if k not in ('results',)}
compact['cases']=[{k:r.get(k) for k in ('case','state','groups','total_wall_s','wall_s','session')} for r in status.get('results',[])]
directory=Path(status['directory']) if 'directory' in status else None
logs=[]
if directory:
    for log in directory.rglob('kit.log'):
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-4500));tail=stream.read().decode('utf-8','replace')
        logs.append({'path':str(log),'bytes':log.stat().st_size,'tail':tail})
print(json.dumps({'status':compact,'logs':logs[-3:],'supervisor_tail':(root/'reports/native_validation_supervisor.log').read_text()[-2000:]}))
