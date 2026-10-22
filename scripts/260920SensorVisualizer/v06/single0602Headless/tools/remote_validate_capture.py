"""Independent ROS/CDR/MCAP readback after native capture and resource release."""
import json
import os
from pathlib import Path
import subprocess
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
sys.path.insert(0,str(root))
from single0602_headless.capture_supervisor import CaptureSupervisor
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
info=json.loads((root/'reports/capture_validation_task.json').read_text())
supervisor=CaptureSupervisor(root,output,output/'runtime/engine.sock')
task=next(x for x in supervisor.status() if x['task_id']==info['task_id'])
assert task['state']=='finished' and task['record_drain_complete'] and task['process_exited'] and task['resource_lock_released'],task
env=os.environ.copy()
for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(name,None)
command=['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','s0602-validate',str(root/'tools/validate_capture_data.py'),task['session']]
result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=90)
(root/'reports/mcap_validation.log').write_text(result.stdout+'\n'+result.stderr)
lines=[x for x in result.stdout.splitlines() if x.startswith('VALIDATION_JSON=')]
report=json.loads(lines[-1].split('=',1)[1]) if lines else {'passed':False,'error':result.stderr[-4000:]}
report.update(exit_code=result.returncode,task=task)
(root/'reports/mcap_validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if result.returncode:raise SystemExit(result.returncode)
