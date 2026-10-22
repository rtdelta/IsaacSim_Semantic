import json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
suite=root/'reports/native_rotation_localization/native007_20261015_v1';results=[]
for p in sorted((suite/'sequences').glob('*/status.json')):
 d=json.loads(p.read_text());results.append({'id':d['id'],'state':d['state'],'completed':len(d['runs']),'planned':d['planned_runs'],'active':d.get('active'),'failure':d.get('failure'),'last_runs':d['runs'][-2:]})
details=[]
for p in suite.glob('*/*/*/*/coordinator_status.json'):
 d=json.loads(p.read_text())
 if d['state'].startswith('FAILED') or d['state'] in ('capturing','analyzing'):
  directory=p.parent;detail={'path':str(directory),'status':d}
  for name in ('continuous_terminal.json','analysis/summary.json'):
   f=directory/name
   if f.is_file():
    v=json.loads(f.read_text());detail[name]={k:v[k] for k in ('status','capture_complete','failure','save_failure','measurement_qualified','ray_model_contract','readback','first_target') if k in v}
  analysis=directory/'analysis.log'
  if d['state']=='FAILED_ANALYSIS' and analysis.is_file():detail['analysis_tail']=analysis.read_text()[-2000:]
  log=directory/'launch.log'
  if log.is_file() and d['state'] in ('capturing','FAILED_CAPTURE'):detail['launch_tail']=log.read_text(errors='replace')[-1800:]
  details.append(detail)
print(json.dumps({'sequences':results,'details':details[-3:],'free_bytes':shutil.disk_usage(root).free}))
