import json,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004')
info=json.loads((root/'reports/latest_suite.json').read_text());out=Path(info['directory']);p=json.loads((out/'progress.json').read_text())
v={'suite':info,'alive':Path('/proc/'+str(info['pid'])).exists(),'state':p['state'],'planned':p['planned_cases'],'completed':len(p['completed_cases']),'cases':p['completed_cases'],'error':p.get('error'),'current':p['current']}
if p['current']:
 case=Path(p['current']['directory']);capture=case/'capture';v['elapsed_s']=(time.monotonic_ns()-p['current']['started_monotonic_ns'])/1e9
 for name in ('groups.jsonl','frames.jsonl'):
  if (capture/name).exists():
   lines=(capture/name).read_text().splitlines();v[name+'_count']=len(lines)
 for name in ('result.json','capture_status.json','engine_error.json'):
  if (capture/name).exists():
   x=json.loads((capture/name).read_text());v[name]={k:x.get(k) for k in ('state','groups','error','engine_exit','recorder_exit') if k in x}
print(json.dumps(v))
