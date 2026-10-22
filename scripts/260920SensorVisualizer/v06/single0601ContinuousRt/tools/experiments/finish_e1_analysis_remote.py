import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
parent=root/'reports/paired_capture_experiments/paired_20261014_e1_scene18_mixed'
results=[]
for repeat in ('r01','r02','r03'):
    p=parent/'repeats'/repeat
    run=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/experiments/analyze_mechanism_relations.py'),str(p)],capture_output=True,text=True)
    results.append({'repeat':repeat,'returncode':run.returncode,'error':run.stderr[-1000:]})
    if run.returncode:raise RuntimeError(run.stderr[-1000:])
run=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/experiments/pack_case_evidence_remote.py'),parent.name],capture_output=True,text=True)
print(json.dumps({'mechanism':results,'pack_returncode':run.returncode,'pack_stdout':run.stdout,'pack_stderr':run.stderr[-2000:]}))
