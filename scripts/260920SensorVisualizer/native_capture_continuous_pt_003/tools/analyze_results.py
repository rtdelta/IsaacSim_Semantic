"""Post-run native evidence summaries; independent of earlier project modules."""
import collections,json,math,sqlite3,statistics,sys
from pathlib import Path

def summary(v):
 v=sorted(float(x) for x in v if x is not None and math.isfinite(float(x)))
 return {'samples':len(v),'mean':statistics.mean(v) if v else None,'min':v[0] if v else None,
   'max':v[-1] if v else None,'p95':v[min(len(v)-1,math.ceil(.95*len(v))-1)] if v else None}

def union(intervals):
 result=0;last=None
 for a,b in sorted((a,b) for a,b in intervals if b>a):
  if last is None:last=[a,b]
  elif a<=last[1]:last[1]=max(last[1],b)
  else:result+=last[1]-last[0];last=[a,b]
 return result+(last[1]-last[0] if last else 0)

def native(path):
 if not path.exists():return {'available':False}
 db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 schema={r[0]:{c[1] for c in db.execute('PRAGMA table_info("'+r[0]+'")')} for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 r=db.execute("SELECT n.start,n.end,n.globalTid FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id WHERE COALESCE(n.text,s.value)='NATIVE_CAPTURE_WINDOW' AND n.end IS NOT NULL").fetchone()
 if r is None:db.close();return {'available':False,'reason':'NVTX window absent'}
 a,b,tid=tuple(r);result={'available':True,'wall_s':(b-a)/1e9,'main_global_tid':tid,'apis':{},'activity':{},'lifecycle':[]}
 gpu=[]
 for table in ['VULKAN_WORKLOAD','CUPTI_ACTIVITY_KIND_KERNEL','CUPTI_ACTIVITY_KIND_MEMCPY','CUPTI_ACTIVITY_KIND_MEMSET']:
  if table not in schema:continue
  intervals=[(max(a,s),min(b,e)) for s,e in db.execute('SELECT start,end FROM '+table+' WHERE start<? AND end>?',(b,a))]
  result['activity'][table]=union(intervals)/1e9;gpu.extend(intervals)
 result['activity']['gpu_union_s']=union(gpu)/1e9
 for table in ['CUPTI_ACTIVITY_KIND_RUNTIME','CUPTI_ACTIVITY_KIND_DRIVER','VULKAN_API','OSRT_API']:
  if table not in schema or 'nameId' not in schema[table]:continue
  q='SELECT s.value api,count(*) calls,sum(min(r.end,?)-max(r.start,?))/1e9 inclusive_wall_s,max(r.end-r.start)/1e6 max_ms FROM '+table+' r JOIN StringIds s ON r.nameId=s.id WHERE r.start<? AND r.end>?'
  params=(b,a,b,a)
  if table=='OSRT_API':q+=' AND r.globalTid=?';params+=(tid,)
  result['apis'][table]=[dict(r) for r in db.execute(q+' GROUP BY s.value ORDER BY inclusive_wall_s DESC LIMIT 20',params)]
  if table.startswith('CUPTI_'):
   result['lifecycle'].extend({'table':table,**dict(r)} for r in db.execute(q+" AND (s.value LIKE 'cuModule%' OR s.value LIKE 'cuLink%') GROUP BY s.value",params))
 schedule=[];entered=None
 if 'SCHED_EVENTS' in schema:
  for t,inside in db.execute('SELECT start,isSchedIn FROM SCHED_EVENTS WHERE globalTid=? ORDER BY start',(tid,)):
   if inside:entered=t
   elif entered is not None:schedule.append((max(a,entered),min(b,t)));entered=None
 result['main_scheduled_s']=union(schedule)/1e9
 if 'COMPOSITE_EVENTS' in schema and 'SAMPLING_CALLCHAINS' in schema:
  result['main_cpu_leaf_modules']=[dict(r) for r in db.execute('SELECT m.value module,count(*) samples FROM COMPOSITE_EVENTS e JOIN SAMPLING_CALLCHAINS c ON c.id=e.id LEFT JOIN StringIds m ON m.id=c.module WHERE c.stackDepth=0 AND e.globalTid=? AND e.start BETWEEN ? AND ? GROUP BY m.value ORDER BY samples DESC LIMIT 15',(tid,a,b))]
 if 'CUPTI_ACTIVITY_KIND_MEMCPY' in schema:
  result['copies']=[dict(r) for r in db.execute('SELECT copyKind,count(*) calls,sum(bytes) bytes,sum(end-start)/1e9 duration_sum_s FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE start>=? AND end<=? GROUP BY copyKind',(a,b))]
 catalog=[]
 for table,cols in schema.items():
  if 'METRIC' in table and table!='GPU_METRICS' and ('metricName' in cols or 'name' in cols):
   catalog.extend(dict(r) for r in db.execute('SELECT * FROM '+table))
 result['metrics']={}
 if 'GPU_METRICS' in schema:
  type_col='typeId' if 'typeId' in schema['GPU_METRICS'] else None
  for row in db.execute('SELECT DISTINCT '+('typeId,' if type_col else '')+'metricId FROM GPU_METRICS'):
   ids=tuple(row);metric=next((c for c in catalog if c.get('metricId')==ids[-1] and (not type_col or c.get('typeId')==ids[0])),{})
   name=metric.get('metricName',metric.get('name',str(ids)))
   rows=list(db.execute('SELECT timestamp,value FROM GPU_METRICS WHERE '+('typeId=? AND ' if type_col else '')+'metricId=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp',ids+(a,b)))
   values=[v for t,v in rows];s=summary(values);s['identity']=ids
   s['valid_for_interpretation']=not (s['max'] is not None and (('[MHz]' in name and (s['max']>10000 or s['min']<0)) or ('[Threads/Warp]' in name and s['max']>32) or ('[GB/s]' in name and s['max']>10000)))
   if not s['valid_for_interpretation']:s['anomaly']='Installed exporter magnitude contradicts unit label; retained raw, not silently normalized.'
   gaps=[y[0]-x[0] for x,y in zip(rows,rows[1:])];median=statistics.median(gaps) if gaps else 0
   s['median_sample_interval_ns']=median;s['large_gap_ns']=sum(g for g in gaps if median and g>3*median)
   result['metrics'][name]=s
 result['limits']=['Instrumented run excluded from ordinary throughput comparison.',
   'Inclusive API wall includes waits and overlap; not pure CPU work.',
   'CUDA+Vulkan interval union is observed GPU activity, not SM occupancy.',
   'GPU metrics cover whole device; sample means do not fill gaps.',
   'Measurement window excludes initialization; absence of steady lifecycle calls does not mean no initial compile.']
 db.close();return result

def analyze(directory):
 out=Path(directory);r=json.loads((out/'result.json').read_text());result={k:r.get(k) for k in ['state','mode','process_wall_s','root_usd_unchanged','capture','error','validation_exit']}
 result['directory']=str(out)
 events=[json.loads(x) for x in (out/'engine_events.jsonl').read_text().splitlines()]
 start=next(x['monotonic_ns'] for x in events if x['event']=='measurement_begin');end=next(x['monotonic_ns'] for x in events if x['event']=='measurement_end')
 frames=[json.loads(x) for x in (out/'frames.jsonl').read_text().splitlines()]
 result['frame_wall_ms']=summary([(x['end_ns']-x['start_ns'])/1e6 for x in frames]);result['inclusive_main_cpu_ms']=summary([x['inclusive_thread_cpu_ns']/1e6 for x in frames])
 rr=[json.loads(x) for x in (out/'resources.jsonl').read_text().splitlines()]
 inside=[x for x in rr if start<=x['host_monotonic_ns']<=end]
 result['nvml_window']={k:summary([x.get('gpu',{}).get(k) for x in inside]) for k in ['utilization.gpu','utilization.memory','memory.used','power.draw']}
 for name in ['kit','recorder']:
  cpus=[]
  for x,y in zip(rr,rr[1:]):
   if not(start<=x['host_monotonic_ns'] and y['host_monotonic_ns']<=end):continue
   p,q=x.get(name),y.get(name)
   if p and q and p['pid']==q['pid'] and p['start_ticks']==q['start_ticks']:
    cpus.append(((q['user_ticks']+q['system_ticks'])-(p['user_ticks']+p['system_ticks']))/q['ticks_per_second']/((y['host_monotonic_ns']-x['host_monotonic_ns'])/1e9))
  result[name+'_cpu_core_equivalents']=summary(cpus)
 result['warning_counts']=dict(collections.Counter(x.split('] [')[-1].split(']')[0] for x in (out/'engine.log').read_text(errors='replace').splitlines() if '[Warning]' in x))
 result['recorder_subscribed_topics']=sorted(set(x.split("Subscribed to topic '")[-1].split("'")[0] for x in (out/'recorder.log').read_text().splitlines() if 'Subscribed to topic' in x))
 if (out/'validation.json').exists():
  v=json.loads((out/'validation.json').read_text());result['validation']={k:v[k] for k in ['ok','errors','mcap_files','measurement_topic_counts','all_sensor_common_stamps','tf_final_comparison']}
  result['validation']['topic_summary']={t:{k:s[k] for k in ['messages','effective_sim_hz','duplicate_stamps','backward_stamps','points','image_encoding','resolution','point_fields'] if k in s} for t,s in v['topics'].items()}
 result['native']=native(out/'native.sqlite')
 (out/'analysis.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
 r=analyze(sys.argv[1]);print(json.dumps({'directory':r['directory'],'state':r['state'],'native':r['native']['available']}))
