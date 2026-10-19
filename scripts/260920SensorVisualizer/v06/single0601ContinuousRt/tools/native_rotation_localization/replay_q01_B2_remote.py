import os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');path=root/'reports/native_rotation_localization/native007_20261015_v1/B2/S0/r01/q01'
env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_rotation_localization/analyze_independent.py'),str(path),'analysis_final'],env=env,check=True)
