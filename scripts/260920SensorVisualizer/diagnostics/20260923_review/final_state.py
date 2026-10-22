from datetime import datetime,timezone
import json,statistics,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/output/sensor_visualizer')
latest=max(p for p in root.iterdir() if p.is_dir() and p.name.startswith('20') and (p/'session.json').exists())
ref=json.loads((latest/'performance_reference.json').read_text());perf=Path(ref['directory'])
status=json.loads((perf/'runtime_status.json').read_text())
rows=[]
with (perf/'resources.jsonl').open() as f:
    for line in f:
        try:r=json.loads(line)
        except ValueError:continue
        if r['unix_time_s']>time.time()-60:rows.append(r)
def mean(v):return statistics.mean(v) if v else None
processes=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        name=(p/'comm').read_text().strip();args=(p/'cmdline').read_bytes()
        if name=='kit' or b'/monitor_resources.py' in args or b'/pack_session_mcap.py' in args or name=='rviz2':
            processes.append(dict(pid=int(p.name),name=name,state=(p/'stat').read_text().split()[2]))
    except OSError:pass
print(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),latest_session=latest.name,current=status,
    monitor_stopped=(perf/'stop').exists(),status_age_s=time.time()-(perf/'runtime_status.json').stat().st_mtime,
    resources_age_s=time.time()-(perf/'resources.jsonl').stat().st_mtime,processes=processes,
    recent_monitor_runs=[dict(name=p.name,stopped=(p/'stop').exists(),state=json.loads((p/'runtime_status.json').read_text()))
        for p in sorted((root/'_performance').iterdir(),reverse=True)[:2] if (p/'runtime_status.json').exists()],
    recent_samples=len(rows),recent_phases=sorted({r['phase'] for r in rows}),
    isaac_cpu_mean_cores=mean([r['processes']['isaac']['cpu_cores'] for r in rows if 'cpu_cores' in r['processes'].get('isaac',{})]),
    gpu_mean_percent=mean([float(g['utilization_percent']) for r in rows if isinstance(r.get('gpu'),list) for g in r['gpu']]),
    current_summary_error=json.loads((perf/'summary.json').read_text()).get('error'))))
