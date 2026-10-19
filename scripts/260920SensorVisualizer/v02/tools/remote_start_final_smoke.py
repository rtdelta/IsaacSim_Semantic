from pathlib import Path
import json
import subprocess
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
for path in root.glob('reports/*_process.json'):
    previous=json.loads(path.read_text()); proc=Path('/proc')/str(previous['pid'])/'cmdline'
    if proc.exists() and str(root) in proc.read_bytes().decode(errors='replace'):
        raise RuntimeError('Owned diagnostic is still running')
job=json.loads((root/'reports/acceptance_job.json').read_text())
job['groups']=3; job['pipeline']['segment_groups']=2
jobpath=root/'reports/final_smoke_job.json';jobpath.write_text(json.dumps(job,indent=2))
logpath=root/f'reports/final_smoke_{time.time_ns()}.log'
with logpath.open('ab') as log:
    proc=subprocess.Popen(['/usr/bin/python3',str(root/'run_capture.py'),'--job',str(jobpath)],cwd=root,
        stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
row={'pid':proc.pid,'log':str(logpath),'job':str(jobpath)}
(root/'reports/capture_process.json').write_text(json.dumps(row));print(json.dumps(row))
