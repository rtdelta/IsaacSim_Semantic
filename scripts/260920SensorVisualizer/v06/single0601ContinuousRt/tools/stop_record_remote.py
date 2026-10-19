"""Terminate only an already finished task-owned GUI stuck in Kit shutdown."""
import json
import os
from pathlib import Path
import signal
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
receipt=json.loads((root/'reports/record_process.json').read_text())
latest=json.loads((root/'reports/acceptance_matrix_actual.json').read_text())
process=Path('/proc')/str(receipt['pid'])
if process.exists() and (process/'stat').read_text().split()[2]!='Z':
    command=(process/'cmdline').read_bytes()
    if b'/kit/kit' not in command or str(root/'run_in_isaac.py').encode() not in command:
        raise RuntimeError('Recorded PID is not the task-owned recorder')
    if not latest['all_requested_cases_executed'] and not any(r['status']=='FAILED' for r in latest['results']):
        raise RuntimeError('Acceptance run is active; refusing to interrupt it')
    os.kill(receipt['pid'],signal.SIGTERM)
    print(json.dumps({'pid':receipt['pid'],'action':'SIGTERM own finished recorder in Kit shutdown'}))
else:
    print(json.dumps({'pid':receipt['pid'],'action':'already_exited'}))
