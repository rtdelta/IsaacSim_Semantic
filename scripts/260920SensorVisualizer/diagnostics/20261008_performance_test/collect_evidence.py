from pathlib import Path
import json,re,statistics as st
from collections import Counter,defaultdict
from datetime import datetime
P=Path('/root/gpufree-data/semantic/output/sensor_visualizer/diagnostics/20261008_perf_02')
report=json.loads((P/'report.json').read_text())
events=[json.loads(s) for s in (P/'events.jsonl').read_text().splitlines()]
resources=[json.loads(s) for s in (P/'resources.jsonl').read_text().splitlines()]
phases=[(datetime.fromisoformat(r['utc']).timestamp(),r['phase']) for r in events if r['kind']=='phase_begin']
issues=defaultdict(Counter)
for line in (P/'kit.log').read_text(errors='replace').splitlines():
    if '[Warning]' not in line and '[Error]' not in line: continue
    try: stamp=datetime.fromisoformat(line.split(' ',1)[0].replace('Z','+00:00')).timestamp()
    except ValueError: continue
    phase=next((name for t,name in reversed(phases) if t<=stamp),'kit_startup')
    msg=re.sub(r'^.*?\[(Warning|Error)\] ',r'[\1] ',line)
    issues[phase][msg]+=1
writers={c['name']:json.loads((Path(c['session'])/'writer_report.json').read_text()) for c in report['captures']}
byphase=defaultdict(list)
for row in resources: byphase[row['phase']].append(row)
resource_summary={}
pid=json.loads((P/'supervisor_result.json').read_text())['pid']
for phase,rows in byphase.items():
    cpu=[s['cpu_cores'] for s in rows]
    gpu=[float(s['gpu'].split(',')[0]) for s in rows if s.get('gpu')]
    main=[t['cpu_cores'] for s in rows for t in s['threads'] if t['tid']==pid]
    resource_summary[phase]={'samples':len(rows),'cpu_mean_cores':st.mean(cpu),'main_mean_cores':st.mean(main) if main else None,
        'gpu_mean_percent':st.mean(gpu) if gpu else None,'gpu_median_percent':st.median(gpu) if gpu else None,
        'gpu_max_percent':max(gpu) if gpu else None,'gpu_min_percent':min(gpu) if gpu else None,
        'cpu_max_cores':max(cpu)}
r={'report':report,'supervisor':json.loads((P/'supervisor_result.json').read_text()),'events':events,'resource_summary':resource_summary,'resource_examples':{phase:rows[len(rows)//2] for phase,rows in byphase.items()},
   'writer_reports':writers,'warnings_by_phase':{p:c.most_common(12) for p,c in issues.items()},
   'mcap_files':[{'path':str(p),'bytes':p.stat().st_size} for p in P.rglob('*.mcap')]}
print(json.dumps(r))
