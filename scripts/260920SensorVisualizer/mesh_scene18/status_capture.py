"""Read only this task's finite capture results and bounded warning excerpts."""
import json,collections
from pathlib import Path
work=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18')
latest=json.loads((work/'latest_capture.json').read_text());case=Path(latest['case'])
out={'latest':latest}
for name in ('result.json','capture_status.json','decoded.json'):
    p=case/name
    if p.is_file():out[name]=json.loads(p.read_text())
for name in ('engine.log','supervisor.log','validation.log','decode.log'):
    p=case/name
    if p.is_file():
        lines=p.read_text(errors='replace').splitlines()
        out[name]={'tail':lines[-16:],'warnings':len([l for l in lines if '[Warning]' in l]),'errors':len([l for l in lines if '[Error]' in l])}
        if name=='engine.log':out[name]['warning_error_examples']=list(dict.fromkeys(l.split('] ',2)[-1] for l in lines if '[Warning]' in l or '[Error]' in l))[:35]
print(json.dumps(out))
