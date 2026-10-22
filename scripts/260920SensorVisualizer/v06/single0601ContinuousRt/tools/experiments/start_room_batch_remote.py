import os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
env=os.environ.copy();env['S0601_BATCH_SPEC']='config/experiments/e2_room_batch.json'
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/experiments/start_batch_remote.py')],env=env,check=True)
