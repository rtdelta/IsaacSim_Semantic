import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');out=[]
for track in (root/'reports/native_owner').glob('*_task.json'):
    info=json.loads(track.read_text());p=Path(info['directory']);status=json.loads((p/'status.json').read_text()) if (p/'status.json').exists() else {}
    proc=Path('/proc')/str(info['pid']);alive=proc.exists() and bool((proc/'cmdline').read_bytes())
    log=(p/'kit.log').read_text(errors='replace');errors=[l for l in log.splitlines() if '[Error]' in l or 'Traceback' in l or 'Exception' in l]
    out.append({'mode':info['mode'],'task_id':info['task_id'],'alive':alive,'status':status,'errors':errors[-6:]})
print(json.dumps({'tasks':out,'gpu':subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True).stdout}))
