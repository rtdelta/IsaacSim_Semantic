import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_rotation_localization/native007_20261015_v1');out=[]
for p in (root/'stage_analysis/T3').glob('pair*.json'):
 d=json.loads(p.read_text());out.append({'file':p.name,'qualified':d['comparison_qualified'],'first_scan':d['scan_semantics'][0],
 'changed_semantic_keys':sorted({k for r in d['scan_semantics'] for k,v in r['same_semantic_fields'].items() if not v}),
 'ray_sets_match':all(r['same_full_valid_ray_set'] for r in d['targets']),'first_target':d['targets'][0]})
print(json.dumps(out))
