"""Read-only inventory of recent production recordings and existing telemetry."""
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,os,re,shutil,time
from pathlib import Path

PROJECT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
OUTPUT=Path('/root/gpufree-data/semantic/output/sensor_visualizer')
report={'utc':datetime.now(timezone.utc).isoformat(),'sessions':[],'monitors':[],'processes':[],'logs':[]}
def read_json(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return None
def file_state(path):
    s=path.stat();return dict(name=path.name,bytes=s.st_size,mtime=s.st_mtime)
folders=sorted((p for p in OUTPUT.iterdir() if p.is_dir() and re.match(r'^20\d{6}_',p.name)),key=lambda p:p.name,reverse=True)
for folder in folders[:3]:
    row={'path':str(folder),'files':[file_state(p) for p in folder.iterdir() if p.is_file()]}
    session=read_json(folder/'session.json') or {}
    row['session']={k:session.get(k) for k in ('created_utc','ended_utc','state','returncode','pid','simulation_pacing','root_frame','world_frame','control_mode')}
    row['scene']={k:session.get('scene',{}).get(k) for k in ('stage','stage_identifier','camera_configs','simulation_pacing')}
    row['lidars']=[s.get('id') for s in session.get('sensors',[])]
    for name in ('capture_summary.json','unified_export_status.json','unified_export_report.json','performance_reference.json'):
        data=read_json(folder/name)
        if data is not None:row[name]={k:v for k,v in data.items() if k not in ('original_message_digests','output_message_digests')}
    row['bags']={p.name:[file_state(f) for f in p.iterdir() if f.is_file()] for p in folder.glob('bag*') if p.is_dir()}
    row['camera_frames']=[]
    for p in folder.glob('cameras/*/frames.jsonl'):
        count=0;first=last=None
        with p.open() as f:
            for line in f:
                try:data=json.loads(line)
                except ValueError:continue
                if first is None:first=data
                last=data;count+=1
        row['camera_frames'].append(dict(id=p.parent.name,count=count,first_ns=first.get('simulation_time_ns') if first else None,
            last_ns=last.get('simulation_time_ns') if last else None,metadata_mtime=p.stat().st_mtime))
    for name in ('recorder.log','unified_export.log'):
        p=folder/name
        if p.exists():
            with p.open('rb') as f:f.seek(max(0,p.stat().st_size-4500));row[name]=f.read().decode(errors='replace')
    report['sessions'].append(row)
monitors=OUTPUT/'_performance'
if monitors.exists():
    for folder in sorted((p for p in monitors.iterdir() if p.is_dir()),reverse=True)[:3]:
        row={'path':str(folder),'stopped':(folder/'stop').exists()}
        for name in ('runtime_status.json','summary.json'):
            data=read_json(folder/name)
            if data is not None:row[name]=data
        p=folder/'resources.jsonl'
        if p.exists():
            with p.open('rb') as f:f.seek(max(0,p.stat().st_size-20000));lines=f.read().decode(errors='replace').splitlines()
            samples=[]
            for line in lines:
                try:samples.append(json.loads(line))
                except ValueError:pass
            row['last_resources']=samples[-3:];row['resource_mtime']=p.stat().st_mtime
        report['monitors'].append(row)
logs=set()
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        args=(p/'cmdline').read_bytes().decode(errors='replace').split('\0')
        name=(p/'comm').read_text().strip()
        role='kit' if name=='kit' else 'rviz' if any('rviz2' in a for a in args) else 'packer' if any(a.endswith('/pack_session_mcap.py') for a in args) else 'monitor' if any(a.endswith('/monitor_resources.py') for a in args) else 'recorder' if 'record' in args and any('ros2' in a for a in args) else None
        if not role:continue
        stat=(p/'stat').read_text();parts=stat[stat.rfind(')')+2:].split()
        info=dict(pid=int(p.name),role=role,state=parts[0],cpu_ticks=int(parts[11])+int(parts[12]),start_ticks=int(parts[19]),
            rss_mib=int(parts[21])*os.sysconf('SC_PAGE_SIZE')/2**20,threads=int(parts[17]))
        if role=='kit':
            for fd in (p/'fd').iterdir():
                try:
                    target=fd.readlink()
                    if str(target).endswith('.log') and target.is_file():logs.add(target)
                except OSError:pass
        report['processes'].append(info)
    except (OSError,ValueError):pass
for path in sorted(logs,key=lambda p:p.stat().st_mtime,reverse=True)[:2]:
    with path.open('rb') as f:f.seek(max(0,path.stat().st_size-600000));lines=f.read().decode(errors='replace').splitlines()
    warnings=[l for l in lines if '[Warning]' in l];errors=[l for l in lines if '[Error]' in l or 'Traceback (most recent call last)' in l]
    report['logs'].append(dict(path=str(path),mtime=path.stat().st_mtime,bytes=path.stat().st_size,
        errors=[l[:1200] for l in errors[-20:]],error_count_in_tail=len(errors),warning_count_in_tail=len(warnings),
        repeated=Counter(re.sub(r'^.*?\[Warning\]\s*','',l) for l in warnings).most_common(8),
        project_events=[l[:1200] for l in lines if '[LidarVisualizer]' in l][-24:]))
report['source_hashes']={name:hashlib.sha256((PROJECT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in (
    'sensor_visualizer/unified_bag.py','sensor_visualizer/performance.py','sensor_visualizer/runtime.py','config/sensors.json')}
report['disk_free_gib']=shutil.disk_usage(OUTPUT).free/2**30
print(json.dumps(report))
