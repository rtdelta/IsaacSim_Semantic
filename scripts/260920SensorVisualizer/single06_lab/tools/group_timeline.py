"""Sequential host stages plus explicitly aligned device metrics for one group."""
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.analysis import load_rows
p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--group',type=int,default=1);a=p.parse_args()
out=Path(a.directory);analysis=json.loads((out/'analysis.json').read_text());rows=load_rows(out)
selected={'lab.RecordPipeline.reserve','lab.SceneStepper.advance_clock','lab.SceneStepper.apply_snapshot',
 'lab.SensorDrivers.warm_cameras','lab.SensorDrivers.acquire','lab.RecordPipeline.submit'}
stages=sorted([r for r in rows if r['event']=='span_end' and r.get('name') in selected and r.get('group_id')==a.group],key=lambda r:r['start_ns'])
origin=min((r['start_ns'] for r in stages),default=0);native=analysis.get('native',{});result=[]
for r in stages:
 name=r['name'];scope=next((s for s in native.get('stages',{}).values() if s['label'].startswith('SV06 '+name+' g='+str(a.group)+' ')),None)
 row={'order':len(result)+1,'group_id':a.group,'name':name,'host_start_offset_ms':(r['start_ns']-origin)/1e6,
  'host_wall_ms':r['duration_ns']/1e6,'host_inclusive_thread_cpu_ms':r.get('thread_cpu_duration_ns',0)/1e6,
  'main_thread_scheduled_ms':scope['main_thread_scheduled_s']*1000 if scope else None,
  'recorded_gpu_work_interval_union_ms':scope['gpu_activity_union_s']*1000 if scope else None,
  'SM_active_mean_percent':None,'SM_issue_mean_percent':None,'Tensor_active_mean_percent':None,'GR_active_mean_percent':None,
  'RTCORE_throughput_mean_percent':None,'SM_throughput_mean_percent':None,'VRAM_throughput_mean_percent':None}
 if scope:
  key=next(k for k,v in native['stages'].items() if v is scope)
  for metric,column in [('SMs Active [Throughput %]','SM_active_mean_percent'),('SM Issue [Throughput %]','SM_issue_mean_percent'),
    ('Tensor Active [Throughput %]','Tensor_active_mean_percent'),('GR Active [Throughput %]','GR_active_mean_percent'),
    ('RTCORE Throughput [Throughput %]','RTCORE_throughput_mean_percent'),('SM Throughput [Throughput %]','SM_throughput_mean_percent'),
    ('VRAM Throughput [Throughput %]','VRAM_throughput_mean_percent')]:
   row[column]=native.get('gpu_metrics',{}).get(metric,{}).get('per_stage_samples',{}).get(key,{}).get('mean')
 result.append(row)
with (out/('group_'+str(a.group)+'_timeline.csv')).open('w',newline='',encoding='utf-8-sig') as f:
 if result:
  writer=csv.DictWriter(f,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
print(json.dumps({'rows':result,'limits':['Ordered host stages; scopes may contain other Kit callbacks.',
 'Blank native values mean outside selected native scopes, not zero load.',
 'GPU metrics are whole-device samples; work-interval union is not SM occupancy.']},indent=2))
