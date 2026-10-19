"""Terminate only a completed task-owned probe, never the existing GUI."""
from pathlib import Path
import json
import os
import signal
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
record = json.loads((root/'reports/probe_process.json').read_text())
pid = int(record['pid'])
proc = Path('/proc')/str(pid)
if proc.exists():
    args = (proc/'cmdline').read_bytes().decode(errors='replace')
    if str(root/'tools/probe_capture.py') not in args or '--no-window' not in args:
        raise RuntimeError('PID no longer belongs to this headless probe')
    report = json.loads((root/'reports/probe_capture.json').read_text())
    if report['state'] not in ('finished', 'failed'): raise RuntimeError('Probe not finished')
    os.kill(pid, signal.SIGTERM)
    print(json.dumps({'pid': pid, 'signal': 'SIGTERM', 'reason': 'completed probe did not exit after post_quit'}))
base = Path('/root/isaacsim')
for p in (base/'exts').glob('isaacsim.simulation_app/**/simulation_app.py'):
    lines = p.read_text(errors='replace').splitlines()
    indexes = [i for i,l in enumerate(lines) if any(s in l for s in ('ignoreUnsaved', 'def close', 'post_quit', 'fast_shutdown', 'os._exit'))]
    ranges = sorted(set(j for i in indexes for j in range(max(0,i-2), min(len(lines), i+10))))
    print(str(p)+'\n'+'\n'.join(f'{i+1}: {lines[i]}' for i in ranges))
