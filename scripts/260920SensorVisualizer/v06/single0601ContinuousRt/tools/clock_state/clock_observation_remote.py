"""Derived native-source delivery latency and verified-seconds stage clocks."""
import collections,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency/clock_20261014_v1')
def rows(p):return [json.loads(s)['data'] for s in p.read_text().splitlines()] if p.exists() else []
output={}
for condition in ('qualification_B','qualification_static'):
    directory=root/condition/'repeats/r01/continuous';events={r['receipt_seq']:r for r in rows(directory/'native_events.jsonl')+rows(directory/'unassigned_events.jsonl')}
    delta=collections.defaultdict(collections.Counter);latency=collections.Counter();latency_steps=collections.Counter()
    for row in rows(directory/'phase_clock_trace.jsonl'):
        value=row.get('external_simulation_time_typed',{}).get('value')
        if isinstance(value,(int,float)):delta[row['phase']][round(value*1e9)-int(row['simulation_time_ns'])]+=1
        if row['phase']=='writer_enter':
            event=events.get(row['extra']['diagnostic_sequence'])
            if event and event.get('source_time_ns'):
                latency[int(row['simulation_time_ns'])-int(event['source_time_ns'])]+=1
                if event.get('physical_step') is not None:latency_steps[row['physical_step']-event['physical_step']]+=1
    output[condition]={'external_minus_physics_ns_by_stage':{k:dict(v) for k,v in delta.items()},
        'callback_physics_minus_native_source_ns':dict(latency),'callback_step_minus_native_source_step':dict(latency_steps),
        'scope':'delivery latency is not a retimestamping rule; geometry compares the exact source-step actual state'}
print(json.dumps(output))
