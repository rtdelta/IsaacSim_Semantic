import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/compare_bridge.py')],capture_output=True,text=True,check=True)
print(r.stdout)
