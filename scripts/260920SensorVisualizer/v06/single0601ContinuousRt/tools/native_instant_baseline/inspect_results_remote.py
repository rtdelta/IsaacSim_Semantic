import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_instant_baseline')
out=[]
for p in sorted(root.glob('native005_*/**/analysis/summary.json')):
    s=json.loads(p.read_text());r={k:v for k,v in s.items() if k not in ('first_target','spec')};r.update(path=str(p),spec={k:s['spec'][k] for k in ('group','profile','run_id','repeat')})
    if s.get('measurement_qualified') is not True:
        r['bad_inputs']=[x for x in json.loads((p.parent/'input_checks.json').read_text()) if not x['ok']][:8]
        r['crosscheck_first']=json.loads((p.parent/'independent_crosscheck.json').read_text())[:2]
        r['first_target']=s.get('first_target')
    out.append(r)
print(json.dumps(out))
