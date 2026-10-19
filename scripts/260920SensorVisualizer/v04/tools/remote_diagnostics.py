from pathlib import Path
from collections import Counter
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
out=Path(json.loads((root/'reports/latest_test.json').read_text())['directory']);result={}
for folder in (out/'captures'/'runs').glob('*/diagnostics'):
    item={}
    for file in folder.glob('summary*.json'):
        try:item[file.name]=json.loads(file.read_text())
        except ValueError:pass
    for file in folder.glob('events_*.jsonl'):
        events=[]
        for line in file.read_text().splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        open_spans={e['span_id']:e for e in events if e['event']=='span_begin'}
        for e in events:
            if e['event']=='span_end':open_spans.pop(e['span_id'],None)
        item[file.name]={'counts':dict(Counter(e['event'] for e in events)),
             'pending_spans':[{k:v for k,v in e.items() if k in ('name','phase','group_id','sensor_id','start_ns')} for e in open_spans.values()],
             'tail':[{k:v for k,v in e.items() if k in ('event','name','phase','group_id','sensor_id','reason','status','error','duration_ns')} for e in events[-10:]]}
    manifest=folder/'manifest.json'
    if manifest.exists():
        v=json.loads(manifest.read_text());item['capabilities']={k:v[k] for k in ('warning_capture','warning_capture_error','sensor_capabilities') if k in v}
    result[str(folder)]=item
print(json.dumps(result))
