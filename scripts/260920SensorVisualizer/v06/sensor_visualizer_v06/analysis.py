"""Offline JSONL analysis and Chrome Trace export; no Isaac/ROS imports."""
from collections import Counter,defaultdict
import json
from pathlib import Path
from .contracts import write_json


def distribution(values):
    values=sorted(values)
    return {'count':len(values),'mean_ms':sum(values)/len(values)/1e6,
            'p50_ms':values[(len(values)-1)//2]/1e6,
            'p95_ms':values[min(len(values)-1,int(len(values)*.95))]/1e6,
            'max_ms':values[-1]/1e6} if values else {'count':0}


def analyze(directory,export_trace=False):
    directory=Path(directory);durations=defaultdict(list);sensors=defaultdict(list)
    reasons=Counter();readiness=Counter();pending=[];quality=[];events=[];incomplete_lines=0
    begins={};ends=set();queue_highwater=defaultdict(int);warning_counts=Counter()
    for path in sorted(directory.glob('*.jsonl')):
        if path.name.startswith('anomaly_'):continue
        for line in path.read_text(encoding='utf-8').splitlines():
            try:row=json.loads(line)
            except json.JSONDecodeError:incomplete_lines+=1;continue
            if 'monotonic_ns' not in row:continue
            events.append(row)
            event=row.get('event')
            if event=='span_begin':begins[row['span_id']]=row
            if event=='span_end':
                ends.add(row['span_id'])
                population='cold' if row.get('group_id') in (None,0) else 'steady'
                durations[(row['name'],population)].append(row['duration_ns'])
                if row.get('sensor_id'):sensors[(row['name'],row['sensor_id'])].append(row['duration_ns'])
            if event=='capture_retry':reasons[row.get('reason','unknown')]+=1
            if event in ('callback_received','callback_accepted','ticket_complete'):readiness[event]+=1
            if event=='warning':
                warning_counts[(row.get('code'),row.get('message'))]=max(warning_counts[(row.get('code'),row.get('message'))],row.get('count',1))
            if row.get('pending'):pending.append({k:row.get(k) for k in ('capture_id','group_id','pending','monotonic_ns')})
            if event=='worker_queue_put':queue_highwater[row['queue']]=max(queue_highwater[row['queue']],row['depth'])
            if event=='slot_reserved':queue_highwater['slots']=max(queue_highwater['slots'],row.get('in_use',0))
    for path in directory.glob('summary*.json'):
        try:summary=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError):continue
        if summary.get('telemetry_dropped'):quality.append({'file':path.name,'telemetry_dropped':summary['telemetry_dropped']})
        if summary.get('io_error') or summary.get('state')!='closed':quality.append({'file':path.name,'state':summary.get('state'),'io_error':summary.get('io_error')})
    # Aggregation files have exact final counts; stream samples use powers of two.
    for path in directory.glob('warnings*.json'):
        try:rows=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError):continue
        for row in rows:warning_counts[(row.get('code'),row.get('sample'))]=max(warning_counts[(row.get('code'),row.get('sample'))],row.get('count',1))
    events.sort(key=lambda r:(r['monotonic_ns'],r.get('pid',0),r.get('event_seq',0)))
    warnings=[]
    for (code,message),count in warning_counts.items():
        warnings.append({'code':code,'sample':message,'count':count,'causality':'association only; not proof of cause'})
    warning_windows=[]
    completed=[r for r in events if r['event']=='span_end']
    for row in [r for r in events if r['event']=='warning'][-200:]:
        overlapping=[s for s in completed if s.get('pid')==row.get('pid') and s['start_ns']<=row['monotonic_ns']<=s['monotonic_ns']]
        warning_windows.append({'code':row.get('code'),'phase':row.get('phase'),'group_id':row.get('group_id'),
            'association':'time_inferred','overlapping_spans':[{'name':s['name'],'span_id':s['span_id']} for s in overlapping[-20:]]})
    report={'schema_version':3,'stages':[{'name':name,'population':pop,**distribution(v)} for (name,pop),v in durations.items()],
            'per_sensor':[{'name':name,'sensor_id':sid,**distribution(v)} for (name,sid),v in sensors.items()],
            'retries':dict(reasons),'readiness':dict(readiness),'queue_highwater':dict(queue_highwater),
            'warnings':warnings,'warning_windows':warning_windows,'pending_windows':pending[-100:],
            'kit_update_gaps':distribution([r['interval_ns'] for r in events if r['event']=='kit_update_gap']),
            'log_quality':quality,'incomplete_lines':incomplete_lines,'unclosed_spans':len(set(begins)-ends),
            'notes':['Overlapping spans must not be summed as elapsed time.',
                     'Cold includes initialization and first group of each capture. Source frame unknown stays null.',
                     'CPU/GPU utilization and host waits cannot identify a GPU kernel bottleneck.']}
    write_json(directory/'analysis.json',report)
    if export_trace and events:
        origin=events[0]['monotonic_ns'];trace=[]
        for row in events:
            args={k:v for k,v in row.items() if k not in ('monotonic_ns','start_ns','duration_ns','utc')}
            if row['event']=='span_begin':continue
            item={'name':row.get('name',row['event']),'pid':row.get('pid',0),'tid':row.get('tid',0),
                  'ts':(row['monotonic_ns']-origin)/1000,'args':args,'cat':row.get('process_role','unknown')}
            if row['event']=='span_end':
                # Async IDs avoid pretending coroutine wall spans are nested CPU zones.
                ident=row['span_id'];begin={**item,'ph':'b','id':ident,'ts':(row['start_ns']-origin)/1000}
                trace.extend([begin,{**item,'ph':'e','id':ident}])
            else:item.update(ph='i',s='t');trace.append(item)
        write_json(directory/'trace.json',{'traceEvents':trace,'displayTimeUnit':'ms',
                                          'metadata':{'relative_host_origin_ns':str(origin)}})
    return report


def compare_manifests(first,second):
    keys=('render_actual','job')
    a=json.loads((Path(first)/'manifest.json').read_text(encoding='utf-8'))
    b=json.loads((Path(second)/'manifest.json').read_text(encoding='utf-8'))
    differences=[]
    for key in keys:
        if a.get(key)!=b.get(key):differences.append(key)
    return {'comparable_configuration':not differences,'different_fields':differences,
            'note':'Configuration equality alone does not prove identical hardware or workload.'}
