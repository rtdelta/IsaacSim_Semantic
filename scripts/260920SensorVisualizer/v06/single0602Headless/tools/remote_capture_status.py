"""Task-scoped process, drain, lease and log observations."""
import json
from pathlib import Path
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
sys.path.insert(0,str(root))
from single0602_headless.capture_supervisor import CaptureSupervisor
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
service=CaptureSupervisor(root,output,output/'runtime/engine.sock')
rows=service.status()
result={'tasks':rows,'resource_lock_busy':service.resource_busy()}
info=json.loads((root/'reports/capture_validation_task.json').read_text())
log=Path(info['directory'])/'kit.log'
if log.is_file():result['log_tail']=log.read_text(errors='replace').splitlines()[-14:]
print(json.dumps(result))
