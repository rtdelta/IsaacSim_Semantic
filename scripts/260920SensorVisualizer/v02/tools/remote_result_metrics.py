"""Read bounded result summaries for this project's finished captures."""
from pathlib import Path
import json
import statistics
root=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v02')
sessions=[p.parent for p in sorted(root.glob('20*/session.json')) if json.loads(p.read_text())['state']=='finished']
session=sessions[-1]
status=json.loads((session/'session.json').read_text())
writer=json.loads((session/'writer_report.json').read_text())
resources=[json.loads(x) for x in (session/'performance/resources.jsonl').read_text().splitlines()]
phases={}
for row in resources:
    phase=phases.setdefault(row['phase'],{'isaac_cpu':[],'worker_cpu':[],'whole_gpu':[]})
    for name,key in [('isaac','isaac_cpu'),('record_worker','worker_cpu')]:
        value=row['processes'].get(name,{}).get('cpu_cores')
        if value is not None: phase[key].append(value)
    try: phase['whole_gpu'].append(float(row['whole_gpu'].split(',')[0]))
    except (ValueError,TypeError,KeyError): pass
print(json.dumps({'session':str(session),'status':status,'writer':writer,
 'performance':json.loads((session/'performance/summary.json').read_text()),
 'resources':{p:{k:{'mean':statistics.mean(v),'max':max(v),'samples':len(v)} for k,v in values.items() if v} for p,values in phases.items()},
 'mcap_bytes':sum(p.stat().st_size for p in (session/'bag_unified').glob('*.mcap'))}))
