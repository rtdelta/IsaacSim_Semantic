import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
x=json.loads((root/'reports/latest_execution.json').read_text());out=Path(x['directory'])
result={'execution':x,'supervisor_exists':Path('/proc',str(x['pid'])).exists()}
for name in ['result.json','engine_result.json','engine_error.json','validation.json','wave_progress.json']:
 p=out/name
 if p.exists():
  v=json.loads(p.read_text())
  if name=='validation.json':v={k:v[k] for k in ['ok','errors','mcap_files']};v['topics']=len(json.loads(p.read_text())['topics'])
  if name=='result.json' and 'validation' in v:
   v['validation']={k:v['validation'][k] for k in ['ok','errors','mcap_files']}
  result[name]=v
for name in ['engine.log','recorder.log','validation.log']:
 p=out/name
 if p.exists():result[name+'_tail']='\n'.join(p.read_text(errors='replace').splitlines()[-18:])
p=out/'engine_events.jsonl'
if p.exists():result['events_tail']=[json.loads(x) for x in p.read_text().splitlines()[-5:]]
print(json.dumps(result,ensure_ascii=False))
