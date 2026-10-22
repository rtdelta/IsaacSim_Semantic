"""Stop exactly the recorded project-owned diagnostic process; retain its evidence."""
import json
import os
from pathlib import Path
import signal
import time

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
record = json.loads((root/'reports/probe_process.json').read_text())
pid = record['pid']
process = Path('/proc')/str(pid)
if process.exists():
    command = (process/'cmdline').read_bytes()
    state = (process/'stat').read_text().split()[2]
    if state == 'Z':
        print(json.dumps({'pid': pid, 'action': 'already_exited_zombie'}))
    elif b'/kit/kit' in command and any(str(root/name).encode() in command for name in ('tools/probe_capabilities.py','tools/probe_barrier.py')):
        os.kill(pid, signal.SIGTERM)
        result = {'pid': pid, 'action': 'SIGTERM exact recorded project-owned hung probe', 'monotonic_ns': str(time.monotonic_ns())}
        (root/'reports/probe_interruption.json').write_text(json.dumps(result))
        print(json.dumps(result))
    else:
        raise RuntimeError('Recorded PID no longer identifies this project probe; refusing signal')
else:
    print(json.dumps({'pid': pid, 'action': 'already_exited'}))
