import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text())
out=Path(latest['directory']);capture=out/'capture'
result={'latest':latest}
for name in ('result.json','capture_status.json'):
    p=capture/name
    if p.is_file():
        value=json.loads(p.read_text())
        if name=='result.json':value={key:value.get(key) for key in ('exit_code','process_wall_s','completed_utc','validation_exit_code','supervised_pid')}
        result[name]=value
for name in ('supervisor.log','capture/engine.log'):
    p=out/name
    if p.is_file():
        with p.open('rb') as f:
            f.seek(max(0,p.stat().st_size-2000));tail=f.read().decode(errors='replace')
        result[name]={'bytes':p.stat().st_size,'tail':tail if result.get('result.json',{}).get('exit_code') not in (None,0) else 'retained remotely'}
print(json.dumps(result))
