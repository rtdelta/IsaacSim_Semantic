import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
out=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
v={}
for n in ('validation.json','group_validation.json','native_cycles.json'):
 p=out/n
 if not p.exists():continue
 x=json.loads(p.read_text())
 if n=='validation.json':
  v[n]={'errors':x['errors'],'topics':{k:{a:t.get(a) for a in ('messages','header_first_ns','header_last_ns','duplicate_stamps','backward_stamps')} for k,t in x['topics'].items()},'counts':x['measurement_topic_counts']}
 elif n=='group_validation.json':v[n]={'budget':x.get('continuous_pt_budget_validation'),'bounds':x['topic_stamp_bounds']}
 else:v[n]=[{k:c.get(k) for k in ('index','sdk_trigger_time','sdk_capture_time','native_time_s','begin_sim_time','sdk_subframes_at_capture')} for c in x]
v['group_times']=[{k:g.get(k) for k in ('group','native_time_s','native_time_after_s','native_sensor_times_s')} for g in map(json.loads,(out/'groups.jsonl').read_text().splitlines())]
print(json.dumps(v))
