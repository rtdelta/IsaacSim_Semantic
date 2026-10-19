from pathlib import Path
import json
P=Path('/root/gpufree-data/semantic/output/sensor_visualizer/diagnostics/20261008_perf_02')
r={}
for name in ('process.json','phase.json','supervisor_result.json','report.json'):
    p=P/name
    if p.exists(): r[name]=json.loads(p.read_text())
for name in ('kit.log','supervisor.log','events.jsonl','resources.jsonl'):
    p=P/name
    if p.exists():
        with p.open('rb') as f:
            f.seek(0,2); size=f.tell(); f.seek(max(0,size-32768)); data=f.read().decode(errors='replace').splitlines()
        r[name]={'bytes':size,'tail':data[-12:]}
print(json.dumps(r))
