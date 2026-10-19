"""Offline evidence aggregation; rolling status windows are deduplicated by update count."""
from collections import defaultdict
import json
from pathlib import Path
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07');sys.path.insert(0,str(root))
from sensor_visualizer_v07.analysis import analyze,distribution
base=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation')
reports=[]
for result_path in sorted(base.glob('*/validation_result.json')):
    result=json.loads(result_path.read_text());directory=result_path.parent
    metrics=directory/'owner_metrics.jsonl';phases=defaultdict(lambda:defaultdict(list));cursor={};missing=0
    if metrics.exists():
        with metrics.open() as stream:
            for line in stream:
                row=json.loads(line);key=row.get('phase');version=row.get('version');stats=row.get('statistics') or {}
                for receipt in row.get('receipts',[]):
                    if receipt.get('state')=='applied' and receipt.get('accepted_ns'):
                        name='keys' if receipt['action']=='keys' else 'parameters'
                        phases[key][name].append(receipt['completed_ns']-receipt['accepted_ns'])
                    elif receipt.get('state')=='failed':phases[key]['failed_receipts'].append(1)
                updates=stats.get('updates',0);previous=cursor.get(version,0)
                if updates>previous:
                    for field,label in (('owner_ms_samples','owner_cpu_callback'),('frame_gap_samples','owner_gap')):
                        values=stats.get(field,[]);take=min(updates-previous,len(values))
                        phases[key][label].extend(round(v*1e6) for v in values[-take:] if take)
                    missing+=max(0,updates-previous-len(stats.get('frame_gap_samples',[])))
                    cursor[version]=updates
    out={'run':directory.name,'state':result['state'],'gui':result.get('gui'),
         'cases':[],'phase_timings':{phase:{k:distribution(v) if k!='failed_receipts' else len(v) for k,v in values.items()} for phase,values in phases.items()},
         'unobserved_owner_updates':missing,'timing_method':'Receipts are unique; callback/gap arrays deduplicated by updates, phase boundary can differ by one published frame',
         'logging':[]}
    for case in result['results']:
        session=Path(case['session']);reference=session/'diagnostics_ref.json'
        if reference.exists():diag=Path(json.loads(reference.read_text())['directory'])
        else:diag=next(iter(session.parent.glob('runs/*/diagnostics')),None)
        item={key:case.get(key) for key in ('case','groups','total_wall_s','wall_s','session')}
        if diag:
            analysis=analyze(diag)
            item.update(log_quality=analysis['log_quality'],retries=analysis['retries'],queue_highwater=analysis['queue_highwater'],
                        top_stages=sorted(analysis['stages'],key=lambda r:r.get('mean_ms',0),reverse=True)[:12])
            source=[];gpu=defaultdict(list);cpu=[];throttle=0;rss=[];cost=[]
            for path in diag.glob('resources_isaac_*.jsonl'):
                for line in path.open():
                    row=json.loads(line)
                    process=row.get('processes',{}).get('isaac',{})
                    if process.get('cpu_cores') is not None:cpu.append(process['cpu_cores'])
                    if process.get('rss_bytes') is not None:rss.append(process['rss_bytes'])
                    throttle+=row.get('cgroup_cpu_delta',{}).get('nr_throttled',0)
                    if row.get('sampler_wall_ns') is not None:cost.append(row['sampler_wall_ns'])
                    for device in row.get('gpus',[]):
                        try:gpu[device['uuid']].append((float(device['utilization.gpu']),int(device['memory.used'])))
                        except (KeyError,ValueError):pass
            item['resources']={'capture_cpu_mean_cores':sum(cpu)/len(cpu) if cpu else None,
                'capture_cpu_max_cores':max(cpu) if cpu else None,'capture_rss_max_bytes':max(rss) if rss else None,
                'cgroup_nr_throttled_delta':throttle,'sampler_wall':distribution(cost),
                'gpus':{uuid:{'samples':len(rows),'mean_util_percent':sum(r[0] for r in rows)/len(rows),
                             'max_util_percent':max(r[0] for r in rows),'vram_min_mib':min(r[1] for r in rows),
                             'vram_max_mib':max(r[1] for r in rows)} for uuid,rows in gpu.items()}}
            for path in diag.glob('events_isaac_*.jsonl'):
                for line in path.open():
                    row=json.loads(line)
                    if row['event'] in ('producer_array_interface','annotator_source_observed'):source.append(row)
            item['physical_device_observations']=source
        out['cases'].append(item)
    for path in directory.rglob('summary*.json'):
        if path.parent.name!='diagnostics':continue
        summary=json.loads(path.read_text())
        out['logging'].append({'path':str(path.relative_to(directory)),**{key:summary.get(key) for key in
            ('role','state','complete','events_generated','events_written','telemetry_dropped','io_error','python_gc')}})
    (directory/'evidence_summary.json').write_text(json.dumps(out,indent=2))
    reports.append(out)
(root/'reports/evidence_summary.json').write_text(json.dumps(reports,indent=2))
print(json.dumps([{'run':r['run'],'state':r['state'],'gui':r['gui'],
                   'cases':[{k:c.get(k) for k in ('case','groups','wall_s','log_quality')} for c in r['cases']],
                   'logging_not_complete':[v for v in r['logging'] if v.get('complete') is False],
                   'evidence_file':str(base/r['run']/'evidence_summary.json')}
                  for r in reports]))
