import json,hashlib,shutil
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
result={'output':str(out),'disk_free_gib':shutil.disk_usage(out).free/1024**3,'processes':[],'cases':{}}
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  v=p.read_bytes().split(b'\0');s=b' '.join(v)
  if v[0].endswith(b'/kit/kit') or b'lidar_equivalence_006' in s:
   result['processes'].append({'pid':int(p.parent.name),'executable':v[0].decode(errors='replace'),'owned':b'lidar_equivalence_006' in s})
 except OSError:pass
for family in ('native_dual_retry1','legacy_raw'):
 cap=out/family/'capture';d={}
 for name in ('result.json','raw_probe_errors.jsonl','engine_error.json'):
  p=cap/name
  if p.exists():d[name]=p.read_text()[:2200]
 rows=[]
 for p in sorted((cap/'dual_exit').glob('*/*.json')):
  if p.name.endswith(('_object_map.json','_raw_header.json')):continue
  x=json.loads(p.read_text());rows.append(x)
 d.update(samples=len(rows),cpu_cuda_equal=sum(x['cpu_cuda_identical'] for x in rows),cpu_stable=sum(x['cpu_stable'] for x in rows),raw_stable=sum(x['raw_stable'] for x in rows))
 d['focus']=[{k:x[k] for k in ('group','sensor','cpu_points','raw_before')} for x in rows if x['sensor']=='MyNZ3_left']
 d['geometry']=[str(p.relative_to(cap)) for p in (cap/'geometry').glob('*')]
 result['cases'][family]=d
dependencies=json.loads((out/'baseline_pose/dependencies.json').read_text())
result['changed_assets']=[p for p,h in dependencies.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
print(json.dumps(result,indent=2))
