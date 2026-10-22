import os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
env=os.environ.copy()
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[name]='1'
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/branch_analysis.py'),str(root/'reports/clock_state_consistency/clock_20261014_v2')],env=env,check=True,timeout=60)
