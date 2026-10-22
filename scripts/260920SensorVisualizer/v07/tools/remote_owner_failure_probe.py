"""Keep evidence around the first owned controller failure, with bounded output."""
from collections import deque
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
status=json.loads((root/'reports/native_validation_status.json').read_text())
directory=Path(status['directory'])/'v07';around=deque(maxlen=10);first=None
for line in (directory/'runtime/control_events.jsonl').open():
    row=json.loads(line);around.append(row)
    if row['event']=='owner_failed':first=list(around);break
log=directory/'kit.log'
with log.open('rb') as stream:
    stream.seek(max(0,log.stat().st_size-8000));tail=stream.read().decode('utf-8','replace')
print(json.dumps({'first_failure_context':first,'owner_native_tail':tail,'phase':status['phase']}))
