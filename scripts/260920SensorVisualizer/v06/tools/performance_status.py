import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
latest=json.loads((root/'reports/latest_performance_suite.json').read_text());out=Path(latest['directory'])
reports={}
for name in ('owner_ready','sdk_profile','interactive_only_metrics','concurrent_metrics','result','concurrent_status','capture_only_status'):
    p=out/(name+'.json')
    if p.exists():reports[name]=json.loads(p.read_text())
log=(out/'supervisor.log').read_text(errors='replace')
owner=(out/'owner.log').read_text(errors='replace')
errors=[x for x in owner.splitlines() if any(s in x for s in ('Traceback','RuntimeError','AssertionError'))]
lines=owner.splitlines();contexts=['\n'.join(lines[i:i+16]) for i,x in enumerate(lines) if 'Traceback' in x]
print(json.dumps({'latest':latest,'reports':reports,'supervisor_tail':log[-2000:],'owner_errors':errors[-5:],'error_context':contexts[-2:]}))
