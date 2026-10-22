"""Extract only this task's initial file-hash probe from the local audit."""
from pathlib import Path
import os,json
root=Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps/audit/20260923'
found=[]
for path in sorted(root.glob('*.jsonl')):
    with path.open(encoding='utf-8') as stream:
        start=json.loads(next(stream))
        if start.get('data',{}).get('task')!='sensor-visualizer-v02': continue
        for line in stream:
            row=json.loads(line)
            if row.get('event')!='ssh.command.completed': continue
            try: value=json.loads(row['data'].get('stdout',''))
            except (ValueError,TypeError): continue
            if isinstance(value,dict) and isinstance(value.get('files'),dict) and 'kit_processes' in value:
                found.append({'operation_id':start['operation_id'],'time_utc':start['time_utc'],'files':value['files']})
print(json.dumps(found))
