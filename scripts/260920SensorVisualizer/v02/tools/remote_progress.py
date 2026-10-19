from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v02')
session=sorted(root.glob('20*'))[-1]
result={'session':str(session)}
for relative in ('performance/resources.jsonl','performance/timings.jsonl','capture_index.jsonl','record_worker.log'):
    p=session/relative
    if p.is_file(): result[relative]=p.read_text(errors='replace').splitlines()[-5:]
result['processes']=[]
for p in Path('/proc').iterdir():
    if not p.name.isdecimal(): continue
    try:
        command=(p/'cmdline').read_bytes().decode(errors='replace')
        if '260920SensorVisualizer/v02/' in command and any(n in command for n in ('record_worker.py','kit_entry.py')):
            result['processes'].append({'pid':int(p.name),'command':command.replace('\0',' ')[:500],
                'status':[l for l in (p/'status').read_text().splitlines() if l.startswith(('State:','VmRSS:','Threads:'))]})
    except OSError: pass
print(json.dumps(result))
