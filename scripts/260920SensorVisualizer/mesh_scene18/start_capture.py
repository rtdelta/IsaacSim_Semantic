"""Prepare scene18-only validation job and launch its finite supervisor."""
import json,subprocess,sys,time
from pathlib import Path
work=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18')
sys.path.insert(0,str(work))
from runtime import run
assert json.loads((work/'validation.json').read_text())['passed']
case=Path('/root/gpufree-data/semantic/output/mesh_scene18')/time.strftime('smoke_%Y%m%d_%H%M%S',time.gmtime())
script=(work/'prepare_capture.py').read_text().replace('CASE_OUTPUT',repr(str(case)))
p=run(script);print(p.stdout);print(p.stderr)
if p.returncode:raise SystemExit(p.returncode)
with (case/'supervisor.log').open('xb') as log:
    child=subprocess.Popen(['/usr/bin/python3','-u',str(work/'capture_supervisor.py'),str(case)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=work)
state={'case':str(case),'supervisor_pid':child.pid}
(work/'latest_capture.json').write_text(json.dumps(state));print(json.dumps(state))
