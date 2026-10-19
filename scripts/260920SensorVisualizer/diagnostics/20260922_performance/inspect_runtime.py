import collections, hashlib, json, os, re
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
result={'source_files':{},'logs':[],'kit_processes':[]}
for name in ('config/sensors.json','generated/sensors.json','sensor_visualizer/simulation_pacing.py',
             'sensor_visualizer/runtime.py','sensor_visualizer/camera_capture.py','sensor_visualizer/camera_rig.py'):
    p=root/name
    if not p.is_file():continue
    data=p.read_bytes()
    row={'sha256':hashlib.sha256(data).hexdigest(),'mtime':p.stat().st_mtime}
    if p.suffix=='.json':
        d=json.loads(data);cfg=d.get('config',d)
        row['config']={k:cfg[k] for k in ('simulation_pacing','control_mode','ros_domain_id','camera','active_cameras','cameras') if k in cfg}
        row['stage']=d.get('stage');row['sensors']=[{k:s[k] for k in ('id','publish_rate_hz','scan_rate_hz','prim_path') if k in s} for s in cfg.get('sensors',[])]
    result['source_files'][name]=row
logs=set()
for folder in Path('/proc').iterdir():
    if not folder.name.isdigit():continue
    try:
        if (folder/'comm').read_text().strip()!='kit':continue
        args=(folder/'cmdline').read_bytes().decode(errors='replace').split('\0')
        flags=[a for a in args if a.startswith(('--/app/runLoops','--/renderer','--/rtx','--/log/file','--exec'))]
        result['kit_processes'].append(dict(pid=int(folder.name),flags=flags,
            fd_count=len(list((folder/'fd').iterdir())),
            status=[l for l in (folder/'status').read_text().splitlines() if l.startswith(('NSpid:','Threads:','VmRSS:','VmSwap:'))]))
        for link in (folder/'fd').iterdir():
            try:
                name=link.readlink()
                if str(name).endswith('.log') and name.is_file():logs.add(name)
            except OSError:pass
    except OSError:pass
if not logs:
    for base in (Path('/root/.nvidia-omniverse/logs/Kit'),Path('/root/.local/share/ov/logs/Kit')):
        if base.exists():logs.update(base.glob('*/*/*.log'))
for path in sorted(logs,key=lambda p:p.stat().st_mtime,reverse=True)[:2]:
    size=path.stat().st_size
    with path.open('rb') as f:
        f.seek(max(0,size-768*1024));tail=f.read().decode(errors='replace')
    lines=tail.splitlines();warnings=[l for l in lines if '[Warning]' in l or '[Error]' in l or 'Traceback' in l]
    counter=collections.Counter(re.sub(r'^.*?\[(Warning|Error)\]\s*',r'[\1] ',l) for l in warnings)
    result['logs'].append(dict(path=str(path),bytes=size,mtime=path.stat().st_mtime,
        tail_lines=len(lines),warnings_or_errors=len(warnings),repeated=counter.most_common(10),
        recent_relevant=[l[:1000] for l in lines if any(v in l for v in ('LidarVisualizer','RTF','FPS','recording','Recording','CUDA','out of memory','Vulkan','device lost'))][-25:]))
out=Path('/root/gpufree-data/semantic/output/sensor_visualizer')
sessions=sorted([p for p in out.iterdir() if p.is_dir() and (p/'session.json').exists()],key=lambda p:p.stat().st_mtime,reverse=True)[:1] if out.exists() else []
result['latest_recordings']=[]
for folder in sessions:
    row={'path':str(folder),'metadata':{},'camera_ranges':[]}
    meta=json.loads((folder/'session.json').read_text());row['metadata_keys']=list(meta)
    for k in ('created_at','started_at','stopped_at','recording_started_at','recording_stopped_at','simulation_start_time','simulation_end_time','scene','simulation_pacing'):
        if k in meta:
            if k=='scene' and isinstance(meta[k],dict):row['metadata'][k]={a:v for a,v in meta[k].items() if a in ('simulation_pacing','stage','stage_identifier','render_lease')}
            else:row['metadata'][k]=meta[k]
    for filename in ('capture_summary.json','recording.json','metadata.json'):
        p=folder/filename
        if p.is_file() and p.stat().st_size<12000:row[filename]=json.loads(p.read_text())
    for p in folder.glob('cameras/*/frames.jsonl'):
        with p.open() as f:
            first=f.readline();last=first;count=bool(first)
            for line in f: count+=1;last=line
        if first.strip() and last.strip():
            a,b=json.loads(first),json.loads(last)
            row['camera_ranges'].append(dict(id=p.parent.name,count=count,first=a.get('simulation_time'),last=b.get('simulation_time')))
    result['latest_recordings'].append(row)
print(json.dumps(result))
