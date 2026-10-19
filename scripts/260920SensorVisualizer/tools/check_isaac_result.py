import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
result=json.loads((root/'reports/isaac_validation.json').read_text())
if not result.get('passed'):
    raise SystemExit(result.get('error','Isaac validation did not finish'))
print('ISAAC_VALIDATION_PASSED',result['case_count'],'native articulation poses')
