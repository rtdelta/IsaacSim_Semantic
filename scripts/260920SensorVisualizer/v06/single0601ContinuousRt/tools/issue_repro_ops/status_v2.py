import json
from pathlib import Path
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
out = root/'reports/issue_repro/minimal_20261016_v2'
p = out/'status.json'
status = json.loads(p.read_text()) if p.exists() else {'state':'not_started'}
print(json.dumps(status))
if status['state'] == 'stopped_for_inspection':
    active = status.get('active')
    log = out/active/'kit.log'
    if log.exists():
        lines = log.read_text(errors='replace').splitlines()
        print('\n'.join(lines[-40:]))
