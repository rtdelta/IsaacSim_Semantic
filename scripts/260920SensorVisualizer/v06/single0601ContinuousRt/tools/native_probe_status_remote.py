"""Bounded read of this task's native diagnostic receipt and recent log."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
receipt=json.loads((root/'reports/native_probe_process.json').read_text())
proc=Path('/proc')/str(receipt['pid'])
running=proc.exists()
if running:
    try:running=b'/kit/kit' in (proc/'cmdline').read_bytes()
    except FileNotFoundError:running=False
latest=root/'reports/latest_native_probe.json'
state=json.loads(latest.read_text()) if latest.exists() else None
report=Path(state['directory'])/'mechanism_report.json' if state else None
log=Path(receipt['log'])
with log.open('rb') as stream:
    stream.seek(max(0,log.stat().st_size-4500));tail=stream.read().decode(errors='replace')
print(json.dumps({'running':running,'receipt':receipt,'state':state,'report':json.loads(report.read_text()) if report and report.exists() else None,'log_tail':tail}))
