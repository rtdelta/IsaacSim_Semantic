"""Bounded read-only status for task-owned recorder and evidence."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
receipt=json.loads((root/'reports/record_process.json').read_text())
process=Path('/proc')/str(receipt['pid'])
out={'receipt':receipt,'alive':process.exists()}
if process.exists():
    out['process_state']=(process/'stat').read_text().split()[2]
log=Path(receipt['log'])
with log.open('rb') as f:
    f.seek(max(0,log.stat().st_size-3000))
    out['log_tail']=f.read().decode('utf-8','replace')
for filename in ('latest_recording.json','acceptance_matrix_actual.json'):
    if (root/'reports'/filename).exists():
        out[filename]=json.loads((root/'reports'/filename).read_text())
output=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt')
sessions=sorted(output.glob('partial/*/session.json'),key=lambda p:p.stat().st_mtime)
if sessions:
    session=sessions[-1]
    out['current_session']={'path':str(session),'session':json.loads(session.read_text())}
    for filename in ('logs/engine_error.log','logs/worker_stderr.log'):
        p=session.parent/filename
        if p.exists():
            with p.open('rb') as f:
                f.seek(max(0,p.stat().st_size-1800))
                out[filename]=f.read().decode('utf-8','replace')
publish_logs=sorted((root/'reports').glob('publish_*.log'),key=lambda p:p.stat().st_mtime)
if publish_logs:
    p=publish_logs[-1]
    out['publisher_tail']=p.read_text(errors='replace')[-2500:]
print(json.dumps(out))
