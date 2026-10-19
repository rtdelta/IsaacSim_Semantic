import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
cap=out/'native_dual/capture'
print('files:',[str(p.relative_to(cap)) for p in cap.glob('*')])
for p in cap.rglob('*.jsonl'):
 if p.stat().st_size>20_000_000:continue
 lines=[s for s in p.read_text().splitlines() if any(w in s.lower() for w in ('observation_error','observation_failed','traceback','exception'))]
 if lines:print(str(p.relative_to(cap)), '\n'.join(lines[:2])[:18000])
for name in ('validation.log','group_validation.log','engine_error.json','engine_result.json'):
 p=cap/name
 if p.exists():print(name,p.read_text()[-5000:])
exec((R/'operations/read_analysis.py').read_text()) if (R/'operations/read_analysis.py').exists() else None
print('FINAL_ANALYSIS',json.dumps({k:v for k,v in json.loads((out/'analysis/summary.json').read_text()).items() if k!='state_alignment'}))
