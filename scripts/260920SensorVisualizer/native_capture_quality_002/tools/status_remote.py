import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
info=json.loads((root/'reports/latest_execution.json').read_text());out=Path(info['directory']);result={'execution':info,'alive':Path('/proc/'+str(info['pid'])).exists()}
for name in ['result.json','engine_result.json','engine_error.json','group_validation.json']:
 p=out/name
 if p.exists():
  v=json.loads(p.read_text())
  if name=='result.json':
   v={k:v.get(k) for k in ('state','engine_exit','recorder_exit','validation_exit','group_validation_exit','process_wall_s','error')}
  if name=='group_validation.json':
   v={k:v[k] for k in ('ok','errors','topic_stamp_bounds') if k in v}
   v['error_count']=len(v.get('errors',[]));v['errors']=v.get('errors',[])[:4]
  result[name]=v
p=out/'engine_events.jsonl'
if p.exists():result['events']=[json.loads(l) for l in p.read_text().splitlines()[-5:]]
for name in ['engine.log','validation.log','group_validation.log']:
 p=out/name
 if p.exists():result[name+'_tail']='\n'.join(p.read_text(errors='replace').splitlines()[-8:])
print(json.dumps(result))
