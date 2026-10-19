import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
latest=json.loads((R/'reports/latest.json').read_text());out=Path(latest['directory'])
result={'latest':latest}
for rel in ('baseline_pose/ready.json','baseline_pose/failure.txt','progress.json','analysis/summary.json'):
 p=out/rel
 if p.exists():
  try:result[rel]=json.loads(p.read_text())
  except ValueError:result[rel]=p.read_text()[-3500:]
if 'baseline_pose/ready.json' not in result:
 p=out/'baseline_pose/engine.log'
 if p.exists():
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-4000));result['tail']=f.read().decode(errors='replace')
progress=result.get('progress.json',{})
case=progress.get('current') or (progress.get('completed') or [{}])[-1]
if case.get('directory'):
 cap=Path(case['directory'])/'capture'
 for rel in ('capture_status.json','result.json','engine_error.json'):
  p=cap/rel
  if p.exists():
   value=json.loads(p.read_text())
   result['current_'+rel]={k:v for k,v in value.items() if k in ('state','groups','exit_code','engine_exit','error','validation_exit','validation_exit_code','session')}
 if progress.get('state')=='failed':
  for rel in ('supervisor.log','capture/engine.log'):
   p=Path(case['directory'])/rel
   if p.exists():
    with p.open('rb') as f:f.seek(max(0,p.stat().st_size-3500));result[rel]=f.read().decode(errors='replace')
print(json.dumps(result,indent=2))
