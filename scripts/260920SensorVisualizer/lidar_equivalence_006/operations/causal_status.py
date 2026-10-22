import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
p=out/'causal_progress.json';print(p.read_text() if p.exists() else 'not started')
for family in ('legacy_raw_retry1','native_warm128','native_pause'):
 cap=out/family/'capture';rows=[]
 for p in (cap/'dual_exit').glob('*/*.json'):
  if p.name.endswith(('_object_map.json','_raw_header.json')):continue
  rows.append(json.loads(p.read_text()))
 print(json.dumps({'family':family,'rows':len(rows),'cpu_cuda_equal':sum(x['cpu_cuda_identical'] for x in rows),'cpu_stable':sum(x['cpu_stable'] for x in rows),'raw_stable':sum(x['raw_stable'] for x in rows),'focus':[{'group':x['group'],'points':x['cpu_points'],'raw_frame':x['raw_before']['frameId']} for x in rows if x['sensor']=='MyNZ3_left']}))
 p=cap/'result.json'
 if p.exists():
  d=json.loads(p.read_text());print(json.dumps({k:d.get(k) for k in ('state','exit_code','engine_exit','validation_exit','group_validation_exit')}))
 p=cap/'engine_error.json'
 if p.exists():print(p.read_text()[-2000:])
 p=cap/'raw_probe_errors.jsonl'
 if p.exists():print(p.read_text()[:1800])
