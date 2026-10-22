"""Start formal all-sensor capture after the independent interactive process exited."""
import json
from pathlib import Path
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
sys.path.insert(0,str(root))
from single0602_headless.capture_supervisor import CaptureSupervisor
report=json.loads((root/'reports/isaac_acceptance.json').read_text())
assert report['state']=='passed' and report['interactive_socket_closed']
process=json.loads((root/'reports/acceptance_process.json').read_text())
cmdline=Path('/proc',str(process['pid']),'cmdline')
assert not cmdline.exists() or process['entry'].encode() not in cmdline.read_bytes()
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
supervisor=CaptureSupervisor(root,output,output/'runtime/engine.sock')
info=supervisor.start({'mode':'offline','trajectory':report['trajectory'],'groups':5,'sample_hz':10,'ros_preview':False})
(root/'reports/capture_validation_task.json').write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(info))
