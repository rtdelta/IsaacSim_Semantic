import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
base=root/'reports/clock_state_consistency/clock_20261014_v1';env=os.environ.copy()
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[k]='1'
reports=[]
for condition in ('T2_P','T2_Rplus','T2_Rminus','T4_B120_3','T4_C120_6','T4_D60_6'):
    for repeat in ('r01','r02','r03'):
        parent=base/condition/'repeats'/repeat
        if not (parent/'analysis/summary.json').exists():continue
        if not (parent/'analysis/h5_numerical_models.json').exists():
            r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/h5_models.py'),str(parent)],env=env,capture_output=True,text=True,check=True,timeout=30)
            reports.append(json.loads(r.stdout))
print(json.dumps({'new_analyses':reports}))
