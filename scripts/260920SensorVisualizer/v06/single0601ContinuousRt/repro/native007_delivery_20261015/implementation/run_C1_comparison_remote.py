import os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/analyze_C1_comparison.py')],env=env,check=True)
