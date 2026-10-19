import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/continue_declared.py')],check=True)
