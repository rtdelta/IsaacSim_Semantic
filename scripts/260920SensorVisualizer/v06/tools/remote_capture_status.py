import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
info=json.loads((root/'reports/native_owner/offline_task.json').read_text());directory=Path(info['directory'])
status=json.loads((directory/'status.json').read_text()) if (directory/'status.json').exists() else {'state':'starting'}
raw=Path('/proc/'+str(info['pid'])+'/cmdline')
alive=raw.exists() and bool(raw.read_bytes())
log=(directory/'kit.log').read_text(errors='replace')
errors=[x for x in log.splitlines() if '[Error]' in x or 'Traceback' in x or 'Exception' in x]
print(json.dumps({'task':info['task_id'],'process_alive':alive,'status':status,'errors':errors[-20:],
    'tail':log[-6000:] if status.get('state') in ('failed','starting') else log.splitlines()[-3:],
    'gpu':subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True).stdout}))
