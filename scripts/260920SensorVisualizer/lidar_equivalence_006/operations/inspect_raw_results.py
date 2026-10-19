import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
result={}
for family in ('native_dual_retry1','legacy_raw'):
 cap=out/family/'capture';rows=[]
 for p in sorted((cap/'dual_exit').glob('*/*.json')):
  if p.name.endswith(('_object_map.json','_raw_header.json')):continue
  d=json.loads(p.read_text());rows.append({k:d.get(k) for k in ('group','sensor','cpu_points','cpu_stable','cpu_cuda_identical','raw_stable')})
 result[family]={'samples':len(rows),'all_cpu_cuda_equal':all(x['cpu_cuda_identical'] for x in rows),'cpu_stable':all(x['cpu_stable'] for x in rows),'raw_stable':all(x['raw_stable'] for x in rows),'focus':[x for x in rows if x['sensor']=='MyNZ3_left']}
 for n in ('result.json','raw_probe_errors.jsonl'):
  p=cap/n
  if p.exists():result[family][n]=p.read_text()[:2000]
 p=cap/'dual_exit/000/MyNZ3_left.json'
 if p.exists():
  d=json.loads(p.read_text());result[family]['raw_before']=d['raw_before'];result[family]['copy_flags']=[d['original_copy_flag'],d['copy_flag_restored']]
  mp=p.with_name('MyNZ3_left_object_map.json');result[family]['map']=mp.read_text()[:1000] if mp.exists() else None
print(json.dumps(result,indent=2))
