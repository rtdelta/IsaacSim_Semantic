import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory']);cap=out/'native_dual_retry1/capture'
result={}
for name in ('result.json','engine_error.json'):
 p=cap/name
 if p.exists():
  x=json.loads(p.read_text());result[name]={k:v for k,v in x.items() if k in ('state','error','engine_exit','validation_exit','group_validation_exit','traceback')}
rows=[]
for p in sorted((cap/'dual_exit').glob('*/*.json')):
 if p.name.endswith(('_object_map.json','_raw_header.json')):continue
 d=json.loads(p.read_text());rows.append({k:d.get(k) for k in ('group','sensor','cpu_points','cuda_points','cpu_stable','cpu_cuda_identical','raw_stable')}|{'raw_frame':d.get('raw_before',{}).get('frameId'),'raw_elements':d.get('raw_before',{}).get('numElements')})
result['rows']=rows
p=cap/'engine.log'
if not rows and p.exists():
 with p.open('rb') as f:f.seek(max(0,p.stat().st_size-4500));result['tail']=f.read().decode(errors='replace')
print(json.dumps(result,indent=2))

