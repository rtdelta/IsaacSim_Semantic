import os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');env=os.environ.copy()
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[k]='1'
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_instant_baseline/compare_runs.py')],check=True,env=env,timeout=90)
