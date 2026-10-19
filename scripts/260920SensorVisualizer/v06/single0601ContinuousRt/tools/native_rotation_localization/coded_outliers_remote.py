import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_rotation_localization/native007_20261015_v1');out=[]
for p in sorted((root/'stage_analysis/coded').glob('header_*.json')):
 d=json.loads(p.read_text());bad=[r for r in d['targets'] if r['header_midpoint_distance_p95_m']>1e-5];out.append({'run':d['run'],'outliers':bad})
result={'scope':'All preregistered header-midpoint failures, no target exclusion or post-hoc threshold change','runs':out}
(root/'stage_analysis/coded/stable_counterexamples.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
