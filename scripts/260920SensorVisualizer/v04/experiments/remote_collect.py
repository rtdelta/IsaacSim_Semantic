"""Read only experiment evidence. Raw traces and MCAP stay in their remote folders."""
from pathlib import Path
from collections import defaultdict,Counter
import base64,gzip,json,statistics,sqlite3
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
OUT=Path(globals().get('OUT',json.loads((ROOT/'reports/latest_experiment.json').read_text())['directory']))
def load(p):return json.loads(p.read_text())
def stats(v):
    if not v:return None
    v=sorted(v);return {'n':len(v),'mean':statistics.mean(v),'p50':statistics.median(v),'p95':v[min(len(v)-1,int(.95*len(v)))],'max':v[-1]}
r={'directory':str(OUT),'files':{p.name:p.stat().st_size for p in OUT.iterdir() if p.is_file()}}
for name in ('capture_result.json','supervisor_result.json','sdk_probe.json','spec.json'):
    if (OUT/name).exists():r[name]=load(OUT/name)
r['sessions']=[]
for p in (OUT/'captures').glob('*/session.json'):
    session={'directory':str(p.parent),'session':load(p)}
    for name in ('writer_report.json','validation_report.json','render_profile.json','sensor_registry.json'):
        if (p.parent/name).exists():session[name]=load(p.parent/name)
    r['sessions'].append(session)
r['diagnostics']=[]
for folder in (OUT/'captures/runs').glob('*/diagnostics'):
    d={'directory':str(folder),'summaries':{p.name:load(p) for p in folder.glob('summary*.json')}}
    spans=defaultdict(list);groups=defaultdict(dict);gaps=[];resource=defaultdict(list);controls=[];retries=[]
    for p in folder.glob('events_isaac_*.jsonl'):
        for line in p.read_text().splitlines():
            row=json.loads(line);group=row.get('group_id');name=row.get('name');event=row['event']
            if event=='span_end':
                spans[(row.get('phase'),name)].append(row['duration_ns']/1e9)
            if group is not None and event=='phase_changed' and row.get('phase')=='advancing':groups[group].setdefault('start_ns',row['monotonic_ns'])
            if event=='ticket_complete':groups[group]['ticket_complete_ns']=row['monotonic_ns']
            if event=='kit_update_gap':gaps.append({k:row.get(k) for k in ('phase','group_id','monotonic_ns','interval_ns')})
            if event in ('control_requested','control_applied'):controls.append(row)
            if event=='capture_retry':retries.append(row)
    d.update(spans=[{'phase':phase,'name':name,**stats(v)} for (phase,name),v in spans.items()],groups=groups,gaps=gaps,controls=controls,retries=retries)
    for p in folder.glob('resources_*.jsonl'):
        for line in p.read_text().splitlines():
            row=json.loads(line);phase=row.get('phase')
            for role,proc in row.get('processes',{}).items():
                for key in ('cpu_cores','rss_bytes','main_thread_cpu_percent'):
                    if isinstance(proc.get(key),(int,float)):resource[(phase,role,key)].append(proc[key])
                main=proc.get('main_thread',{}).get('cpu_cores')
                if isinstance(main,(int,float)):resource[(phase,role,'main_thread_cpu_percent')].append(main*100)
            for gpu in row.get('whole_gpu','').splitlines():
                parts=gpu.split(',')
                try:
                    resource[(phase,'whole_gpu','utilization_percent')].append(float(parts[1]))
                    resource[(phase,'whole_gpu','memory_used_mib')].append(float(parts[2]))
                except (IndexError,ValueError):pass
            try:resource[(phase,'cgroup','memory_current_bytes')].append(float(row['cgroup_memory.current']))
            except (KeyError,TypeError,ValueError):pass
    d['resources']=[{'phase':p,'role':role,'metric':key,**stats(v)} for (p,role,key),v in resource.items()]
    r['diagnostics'].append(d)
text=(OUT/'kit.log').read_text(errors='replace')
r['warning_counts']=dict(Counter(l.split('[Warning]',1)[1].strip() for l in text.splitlines() if '[Warning]' in l))
r['errors']=[l for l in text.splitlines() if '[Error]' in l or 'Traceback' in l or 'Exception:' in l]
if (OUT/'native.sqlite').exists():
    db=sqlite3.connect(f'file:{OUT}/native.sqlite?mode=ro',uri=True)
    r['native_schema']={n:db.execute('pragma table_info("'+n+'")').fetchall() for (n,) in db.execute('select name from sqlite_master where type="table"')}
    r['native_counts']={n:db.execute('select count(*) from "'+n+'"').fetchone()[0] for n in r['native_schema']}
    db.close()
print(json.dumps({'encoding':'gzip-base64-json','data':base64.b64encode(gzip.compress(json.dumps(r).encode())).decode()}))
