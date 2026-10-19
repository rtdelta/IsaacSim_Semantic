import collections,json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');suite=root/'reports/native_rotation_localization/native007_20261015_v1'
out=[]
for p in sorted((suite/'sequences').glob('*/status.json')):
 d=json.loads(p.read_text());out.append({'id':d['id'],'state':d['state'],'completed':len(d['runs']),'planned':d['planned_runs'],'active':d.get('active',{}).get('spec'),'failure':d.get('failure'),'last':d['runs'][-1:]})
print(json.dumps({'sequences':out,'free_bytes':shutil.disk_usage(root).free}))
