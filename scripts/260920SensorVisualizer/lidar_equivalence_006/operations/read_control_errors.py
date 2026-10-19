import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
for label in ('native_warm128_retry1','native_pause_retry1'):
 cap=out/label/'capture';r={}
 for name in ('validation.json','group_validation.json','engine_error.json'):
  p=cap/name
  if p.exists():
   d=json.loads(p.read_text());r[name]={k:v for k,v in d.items() if k in ('ok','errors','groups','frames','error','traceback')}
 print(json.dumps({'case':label,**r}))
