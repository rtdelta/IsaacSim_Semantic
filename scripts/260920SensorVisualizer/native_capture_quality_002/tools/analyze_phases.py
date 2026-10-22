"""Read-only Nsight SQL scope per NVTX phase; retain sums and interval unions."""
import json,sqlite3,sys,collections
from pathlib import Path
from analyze_results import union,native

def main(directory):
 out=Path(directory);path=out/'native.sqlite'
 if not path.exists():raise FileNotFoundError(path)
 db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 schema={r[0]:{c[1] for c in db.execute('PRAGMA table_info("'+r[0]+'")')} for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 windows=list(db.execute("SELECT n.start,n.end,n.globalTid,COALESCE(n.text,s.value) label FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id WHERE COALESCE(n.text,s.value) LIKE 'NC002_GROUP_%' AND n.end>n.start ORDER BY n.start"))
 phases=[]
 for w in windows:
  a,b,tid,label=tuple(w);row={'label':label,'wall_s':(b-a)/1e9,'apis':{},'activity':{}};gpu=[]
  for table in ('VULKAN_WORKLOAD','CUPTI_ACTIVITY_KIND_KERNEL','CUPTI_ACTIVITY_KIND_MEMCPY','CUPTI_ACTIVITY_KIND_MEMSET'):
   if table not in schema:continue
   intervals=[(max(a,s),min(b,e)) for s,e in db.execute('SELECT start,end FROM '+table+' WHERE start<? AND end>?',(b,a))]
   row['activity'][table]=union(intervals)/1e9;gpu.extend(intervals)
  row['activity']['gpu_union_s']=union(gpu)/1e9
  for table in ('CUPTI_ACTIVITY_KIND_RUNTIME','CUPTI_ACTIVITY_KIND_DRIVER','VULKAN_API','OSRT_API'):
   if table not in schema or 'nameId' not in schema[table]:continue
   q='SELECT s.value api,count(*) calls,sum(min(r.end,?)-max(r.start,?))/1e9 inclusive_wall_s,max(r.end-r.start)/1e6 max_ms FROM '+table+' r JOIN StringIds s ON r.nameId=s.id WHERE r.start<? AND r.end>?'
   params=(b,a,b,a)
   if table=='OSRT_API':q+=' AND r.globalTid=?';params+=(tid,)
   row['apis'][table]=[dict(r) for r in db.execute(q+' GROUP BY s.value ORDER BY inclusive_wall_s DESC LIMIT 12',params)]
  row['gpu_metrics']={}
  if 'GPU_METRICS' in schema:
   catalogs=[t for t in schema if 'METRIC' in t and t!='GPU_METRICS' and 'metricName' in schema[t]]
   for cat in catalogs:
    for metric in db.execute('SELECT * FROM '+cat):
     m=dict(metric);ids=[m['metricId']];where='metricId=?'
     if 'typeId' in schema['GPU_METRICS'] and 'typeId' in m:where+=' AND typeId=?';ids.append(m['typeId'])
     v=list(db.execute('SELECT value FROM GPU_METRICS WHERE '+where+' AND timestamp BETWEEN ? AND ?',(*ids,a,b)))
     if v:row['gpu_metrics'][m['metricName']]={'n':len(v),'mean':sum(x[0] for x in v)/len(v),'min':min(x[0] for x in v),'max':max(x[0] for x in v)}
  phases.append(row)
 result={'whole_window':native(path),'phases':phases,'limits':['API duration sums include waits/overlap. GPU activity union is not SM occupancy.','Device metrics include all processes, exclude unsampled gaps, and require unit sanity checks in whole_window.','Evidence phases are extra observation and PNG encoding, not the production encoder path.']}
 (out/'phase_analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps({'phases':len(phases),'directory':str(out)}));db.close()
if __name__=='__main__':main(sys.argv[1])
