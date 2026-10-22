"""Task-owned report correlation. Whole-card samples are not kernel occupancy."""
import csv,io,json,statistics
from collections import Counter,defaultdict
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
def quantiles(v):
    a=sorted(v)
    return {'n':len(a),'mean':statistics.mean(a),'p95':a[int(.95*(len(a)-1))],'max':a[-1]} if a else None
reports={}
for pointer in ('baseline','motion','optimized','scheduled','diagnostic','keepalive','final'):
    p=root/'reports'/(pointer+'_performance_suite.json')
    if not p.exists():continue
    track=json.loads(p.read_text());out=Path(track['directory']);report={'directory':str(out),'version':track['version']}
    for name in ('spec','result','sdk_profile','owner_ready'):
        f=out/(name+'.json')
        if f.exists():report[name]=json.loads(f.read_text())
    resource=defaultdict(lambda:defaultdict(list));query=[]
    f=out/'resources.jsonl'
    if f.exists():
        for line in f.read_text().splitlines():
            row=json.loads(line);case=row['case'];query.append(row.get('query_ms',0))
            for pid,proc in row['processes'].items():
                for k in ('cpu_cores','rss_kib'):
                    if proc.get(k) is not None:resource[case]['pid_'+pid+'_'+k].append(proc[k])
            for fields in csv.reader(io.StringIO(row.get('whole_gpu',''))):
                if len(fields)==5:
                    for i,k in ((2,'gpu_util_percent'),(3,'gpu_memory_mib')):
                        try:resource[case][k].append(float(fields[i]))
                        except ValueError:pass
    report['resources']={case:{k:quantiles(v) for k,v in values.items()} for case,values in resource.items()}
    report['monitor_query_ms']=quantiles(query)
    report['capture_diagnostics']={}
    for label in ('concurrent','capture_only'):
        jobp=out/(label+'_job.json');statusp=out/(label+'_status.json')
        if not statusp.exists():continue
        status=json.loads(statusp.read_text());session=Path(status['session']);writer=session/'writer_report.json'
        if writer.exists():report['capture_diagnostics'][label]={'writer':json.loads(writer.read_text())}
        runs=out/'captures/runs'
        if runs.exists():
            matching=[]
            for manifest in runs.glob('*/diagnostics/manifest.json'):
                m=json.loads(manifest.read_text())
                if m.get('job',{}).get('replay',{}).get('status_path')!=str(statusp):continue
                d=manifest.parent;queues=defaultdict(list);slots=[]
                for events in d.glob('events_*.jsonl'):
                    for line in events.read_text().splitlines():
                        event=json.loads(line)
                        if event['event']=='worker_queue_put':
                            queues[event['queue']+'_put_wait_ms'].append(event['wait_ns']/1e6)
                            queues[event['queue']+'_depth'].append(event['depth'])
                        if event['event']=='png_started':queues['png_queue_wait_ms'].append(event['queue_wait_ns']/1e6)
                        if event['event']=='slot_reserved':slots.append(event['in_use'])
                matching.append({'directory':str(d),'summary':json.loads((d/'summary.json').read_text()),
                    'writer_summaries':[json.loads(p.read_text()) for p in d.glob('summary_writer_*.json')],
                    'queues':{k:quantiles(v) for k,v in queues.items()},'max_slots_in_use_at_reserve':max(slots,default=0),
                    'warnings':json.loads((d/'warnings.json').read_text())})
            report['capture_diagnostics'].setdefault(label,{})['runs']=matching
    outliers=out/'sdk_outliers.jsonl'
    if outliers.exists():report['sdk_outliers']=[json.loads(x) for x in outliers.read_text().splitlines()]
    frames=[]
    for f in (out/'owner_output/runs').glob('*/diagnostics/events_interactive_*.jsonl'):
        for line in f.read_text().splitlines():
            row=json.loads(line)
            if row['event']=='interactive_frame' and row['duration_ns']>50_000_000:frames.append(row)
    if frames:report['slow_frame_details']=frames
    reports[pointer]=report
(root/'reports/performance_collected.json').write_text(json.dumps(reports,indent=2))
print(json.dumps(reports))
