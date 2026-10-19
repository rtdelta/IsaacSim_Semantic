"""Read only task-owned tests and deployed file hashes; no environment dump."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
result={'runs':[]}
def load(path):return json.loads(path.read_text())
def stats(values):
    if not values:return None
    values=sorted(values)
    return {'count':len(values),'mean':sum(values)/len(values),'p50':values[len(values)//2],
            'p95':values[min(len(values)-1,int(.95*len(values)))],'max':values[-1]}
for pointer in ('latest_test.json','latest_headless_test.json'):
    p=ROOT/'reports'/pointer
    if not p.exists():continue
    out=Path(load(p)['directory']);item={'directory':str(out),'pointer':pointer}
    for name in ('supervisor_result.json','acceptance.json','validation_results.json','job.json'):
        if (out/name).exists():item[name]=load(out/name)
    if 'acceptance.json' not in item:
        item['sessions']=[{'path':str(p.parent),'session':load(p),
                           'writer':load(p.parent/'writer_report.json') if (p.parent/'writer_report.json').exists() else None}
                          for p in (out/'captures').glob('*/session.json')]
    item['diagnostics']=[]
    for folder in (out/'captures'/'runs').glob('*/diagnostics'):
        d={'path':str(folder),'summaries':{},'warnings':[],'resources':{}}
        for file in folder.glob('summary*.json'):d['summaries'][file.name]=load(file)
        if (folder/'manifest.json').exists():
            manifest=load(folder/'manifest.json')
            d['manifest']={k:v for k,v in manifest.items() if k!='code_sha256'}
            d['code_hash_count']=len(manifest.get('code_sha256',{}))
        for file in folder.glob('warnings*.json'):d['warnings']+=load(file)
        measures=defaultdict(list);gaps=[];control=[];retries=[]
        for file in folder.glob('resources_*.jsonl'):
            for line in file.read_text().splitlines():
                row=json.loads(line);phase=row.get('phase','unknown')
                for role,proc in row.get('processes',{}).items():
                    for key in ('cpu_cores','rss_bytes'):
                        if proc.get(key) is not None:measures[(phase,role,key)].append(proc[key])
                for gpu in row.get('whole_gpu','').splitlines():
                    parts=gpu.split(',')
                    try:measures[(phase,'gpu','utilization_percent')].append(float(parts[1]))
                    except (ValueError,IndexError):pass
        d['resources']=[{'phase':k[0],'role':k[1],'metric':k[2],**stats(v)} for k,v in measures.items()]
        for file in folder.glob('events_isaac_*.jsonl'):
            for line in file.read_text().splitlines():
                row=json.loads(line)
                if row['event'] in ('control_requested','control_applied'):control.append(row)
                if row['event']=='capture_retry':retries.append(row)
        d['controls']=control;d['retries']=retries;item['diagnostics'].append(d)
    if (out/'kit.log').exists():
        lines=(out/'kit.log').read_text(errors='replace').splitlines()
        warnings=Counter(line.split('[Warning]',1)[1].strip() for line in lines if '[Warning]' in line)
        item['kit_warnings']=[{'message':k,'count':v} for k,v in warnings.most_common()]
        item['kit_errors']=[line for line in lines if '[Error]' in line]
    result['runs'].append(item)
manifest=load(ROOT/'deployment_manifest.json')
result['deployment_manifest']=manifest
result['active_task_processes']=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        args=p.read_bytes().split(b'\0')
        if args and (args[0].endswith(b'/kit/kit') or any(b'record_worker.py' in a or b'supervise_v04.py' in a for a in args)):
            result['active_task_processes'].append({'pid':int(p.parent.name),'program':args[0].decode(errors='replace')})
    except OSError:pass
print(json.dumps(result))
