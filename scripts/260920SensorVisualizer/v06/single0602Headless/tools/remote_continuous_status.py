"""Read bounded, task-specific native test results."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
for name in ('continuous_probe_process.json','continuous_probe.json','continuous_acceptance_process.json','continuous_acceptance.json',
             'continuous_gui_process.json','continuous_gui.json'):
    path=root/'reports'/name
    if not path.is_file():continue
    row=json.loads(path.read_text())
    if 'steps' in row:
        steps=row.pop('steps');row['step_count']=len(steps);row['first_steps']=steps[:3];row['last_steps']=steps[-2:]
        row['max_velocity']=max((abs(v) for s in steps for name in ('linear','angular','dof') for vector in s[name] for v in vector),default=0.)
    if 'statistics' in row:row['statistics']={k:v for k,v in row['statistics'].items() if not isinstance(v,list)}
    print(json.dumps({'file':name,'report':row}))
path=root/'reports/continuous_capture_regression.json'
if path.is_file():
    row=json.loads(path.read_text())
    print(json.dumps({'file':path.name,'report':row}))
for name in ('continuous_acceptance.log','continuous_gui.log'):
    path=root/'reports'/name
    if path.is_file():
        tail=path.read_bytes()[-18000:].decode(errors='replace')
        selected=[line[:1500] for line in tail.splitlines() if 'S0602_CONTINUOUS_ACCEPTANCE' not in line and any(s in line for s in ('Traceback','Error','Exception','S0602_', 'File "','RuntimeError','AttributeError','AssertionError'))]
        print(json.dumps({'log':name,'selected_tail':selected[-35:]}))
