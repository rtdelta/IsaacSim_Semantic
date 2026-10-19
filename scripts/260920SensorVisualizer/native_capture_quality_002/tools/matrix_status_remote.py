import json,shutil,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002');result={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'disk_free_gib':shutil.disk_usage(root).free/1024**3}
for kind in ('matrix','reference','native_reference'):
 p=root/f'reports/latest_{kind}.json'
 if p.exists():
  v=json.loads(p.read_text());v['alive']=Path('/proc/'+str(v['pid'])).exists();out=Path(v['directory'])
  files=('reference_native_progress.json','reference_native_result.json') if kind=='native_reference' else (f'{kind}_progress.json',f'{kind}_result.json')
  for name in files:
   f=out/name
   if f.exists():v[name]=json.loads(f.read_text())
  result[kind]=v
p=root/'reports/latest_execution.json'
if p.exists():
 v=json.loads(p.read_text());out=Path(v['directory']);v['alive']=Path('/proc/'+str(v['pid'])).exists()
 for name in ('result.json','engine_error.json'):
  f=out/name
  if f.exists():
   r=json.loads(f.read_text());v[name]={k:r.get(k) for k in ('state','engine_exit','validation_exit','group_validation_exit','error') if k in r}
 f=out/'engine_events.jsonl'
 if f.exists():v['events']=[json.loads(l) for l in f.read_text().splitlines()[-3:]]
 f=out/'groups.jsonl'
 if f.exists():v['groups']=len(f.read_text().splitlines())
 result['execution']=v
print(json.dumps(result))
