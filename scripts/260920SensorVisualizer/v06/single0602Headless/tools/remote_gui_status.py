import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless/reports')
for name in ('continuous_gui_process.json','continuous_gui.json'):
    path=root/name
    if not path.exists():continue
    row=json.loads(path.read_text())
    if 'statistics' in row:row['statistics']={k:v for k,v in row['statistics'].items() if not isinstance(v,list)}
    if 'timing_samples' in row:
        rows=row.pop('timing_samples');row['timing_samples']=rows[:4]
    print(json.dumps({'file':name,'report':row}))
path=root/'continuous_gui.log'
if path.is_file():
    lines=path.read_bytes()[-12000:].decode(errors='replace').splitlines()
    print(json.dumps({'error_tail':[line[:1200] for line in lines if 'S0602_CONTINUOUS_ACCEPTANCE' not in line and any(t in line for t in ('Error','Exception','Traceback','File "'))][-15:]}))
    all_lines=path.read_text(errors='replace').splitlines()
    for i,line in enumerate(all_lines):
        if 'timing_probe' in line:
            print(json.dumps({'timing_probe_error':all_lines[max(0,i-3):i+5]}));break
