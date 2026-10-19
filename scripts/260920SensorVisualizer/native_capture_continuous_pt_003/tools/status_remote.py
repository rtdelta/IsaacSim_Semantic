import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
info=json.loads((root/'reports/latest_execution.json').read_text());out=Path(info['directory'])
v={'execution':info,'alive':Path('/proc/'+str(info['pid'])).exists()}
def tail(path,size=250000):
 with path.open('rb') as f:
  f.seek(max(0,path.stat().st_size-size));data=f.read().decode(errors='replace').splitlines()
  return data[-1] if data else None
for name in ('native_updates.jsonl','resources.jsonl'):
 p=out/name
 if p.exists():
  try:
   row=json.loads(tail(p));v[name+'_last']=row if name=='native_updates.jsonl' else {k:row.get(k) for k in ('utc_ns','gpu','sample_error')}
  except (ValueError,TypeError):pass
for name in ('result.json','engine_error.json','continuous_result.json','group_validation.json'):
 p=out/name
 if p.exists():
  r=json.loads(p.read_text())
  v[name]={k:r.get(k) for k in ('state','engine_exit','recorder_exit','validation_exit','group_validation_exit','error','budget_all_frames_passed','frames','app_updates','native_scenario_wall_s','ok','errors') if k in r}
for name in ('engine_events.jsonl','engine.log','group_validation.log'):
 p=out/name
 if p.exists():v[name+'_tail']='\n'.join(p.read_text(errors='replace').splitlines()[-6:])[-3500:]
print(json.dumps(v))
