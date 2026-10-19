"""Read-only aggregation of recorded timing/resource samples and current log."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json,math,re,statistics,time
from pathlib import Path

session=Path('/root/gpufree-data/semantic/output/sensor_visualizer/20260923_102450_024594_6ccb02')
perf=Path(json.loads((session/'performance_reference.json').read_text())['directory'])
def rows(path):
    with path.open() as f:
        for line in f:
            try:yield json.loads(line)
            except ValueError:pass
events=list(rows(perf/'timings.jsonl'))
resources=list(rows(perf/'resources.jsonl'))
boundaries=[r for r in events if r['event']!='span']
start=next(r['monotonic_s'] for r in boundaries if r['event']=='recording_started' and r.get('session')==str(session))
end=next(r['monotonic_s'] for r in boundaries if r['event']=='recording_stopped' and r.get('session')==str(session))
spans=defaultdict(list)
for r in events:
    if r['event']=='span' and start<=r['monotonic_s']<=end:spans[r['name']].append(r['duration_s'])
def stats(values):
    values=sorted(values)
    return dict(n=len(values),mean=statistics.mean(values),min=values[0],max=values[-1],p95=values[min(len(values)-1,int(len(values)*.95))]) if values else None
phases=defaultdict(list)
for r in resources:phases[r.get('phase','unknown')].append(r)
phase_summary={}
for phase,points in phases.items():
    values=defaultdict(list)
    for row in points:
        for role,data in row['processes'].items():
            for field in ('cpu_cores','rss_kib','read_bytes_per_s','write_bytes_per_s'):
                if field in data:values[role+'.'+field].append(data[field])
        if isinstance(row.get('gpu'),list):
            for gpu in row['gpu']:
                for field in ('utilization_percent','memory_used_mib','power_w'):
                    try:values['gpu.'+field].append(float(gpu[field]))
                    except (ValueError,KeyError):pass
        values['heartbeat_age_s'].append(row.get('kit_heartbeat_age_s',0))
    phase_summary[phase]=dict(samples=len(points),first_utc=datetime.fromtimestamp(points[0]['unix_time_s'],timezone.utc).isoformat(),
        last_utc=datetime.fromtimestamp(points[-1]['unix_time_s'],timezone.utc).isoformat(),metrics={k:stats(v) for k,v in values.items()})
recorded=[r for r in resources if start<=r['monotonic_s']<=end]
periods=[]
for a,b in zip(boundaries,boundaries[1:]):
    if a['event']=='phase':
        following=next((r for r in boundaries if r['event']=='phase' and r['monotonic_s']>a['monotonic_s']),None)
        periods.append(dict(phase=a['phase'],utc=a['utc'],simulation_time=a.get('simulation_time'),
            duration_s=(following['monotonic_s'] if following else resources[-1]['monotonic_s'])-a['monotonic_s']))
trace_summary={k:dict(count=len(v),total_s=sum(v),**stats(v)) for k,v in spans.items()}
log=Path('/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0/kit_20260923_095639.log')
runtime_start=next(r['utc'][:19] for r in boundaries if r['event']=='runtime_started')
warnings=Counter();errors=[];project=[]
for line in log.read_text(errors='replace').splitlines():
    if not line.startswith('2026-09-23T') or line[:19]<runtime_start:continue
    if '[Warning]' in line:warnings[line.split('[Warning]',1)[1].strip()]+=1
    if '[Error]' in line or 'Traceback' in line:errors.append(line[:1200])
    if '[LidarVisualizer]' in line and 'Groups' not in line:project.append(line[:1200])
print(json.dumps(dict(session=str(session),performance=str(perf),recording_wall_event_s=end-start,
    recording_spans=trace_summary,phases=phase_summary,phase_intervals=periods,events=boundaries,
    cgroup_at_record_start=recorded[0]['cgroup'] if recorded else None,cgroup_at_record_end=recorded[-1]['cgroup'] if recorded else None,
    log=dict(from_utc=runtime_start,errors=errors,warning_count=sum(warnings.values()),repeated=warnings.most_common(12),project_events=project))))
