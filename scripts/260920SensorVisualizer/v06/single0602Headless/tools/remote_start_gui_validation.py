"""Start the owned GUI on the existing X11 desktop without touching other Kit processes."""
import json
from pathlib import Path
import subprocess
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
sys.path.insert(0,str(root))
from run_capture import launch_spec
from single0602_headless.capture_supervisor import CaptureSupervisor
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
assert not CaptureSupervisor(root,output,output/'runtime/engine.sock').resource_busy()
command,env,cwd=launch_spec(root/'config/interactive.json',True,root/'tools/gui_input_entry.py')
assert Path('/tmp/.X11-unix/X20').exists()
env['DISPLAY']=':20'
if Path('/root/.Xauthority').is_file():env['XAUTHORITY']='/root/.Xauthority'
with (root/'reports/gui_input.log').open('ab') as log:
    process=subprocess.Popen(command,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
info={'pid':process.pid,'entry':str(root/'tools/gui_input_entry.py')}
(root/'reports/gui_process.json').write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(info))
