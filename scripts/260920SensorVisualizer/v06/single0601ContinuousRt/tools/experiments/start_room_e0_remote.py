import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/experiments/start_paired_remote.py'),'--spec',str(root/'config/experiments/e0_room.json')],check=True)
