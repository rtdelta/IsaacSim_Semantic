import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/coordinator.py'),'--batch',str(root/'config/clock_state/t2_qualification_batch.json')],check=True)
