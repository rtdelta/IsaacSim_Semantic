"""Read-only SQL analysis: CPU scheduled time and unioned GPU work intervals."""
from pathlib import Path
import base64,gzip,json,sqlite3
OUT=Path(globals().get('OUT','/root/gpufree-data/semantic/output/sensor_visualizer/v04/experiments/20261009_120516_859377_native_v03'))
db=sqlite3.connect(f'file:{OUT}/native.sqlite?mode=ro',uri=True);db.row_factory=sqlite3.Row
def query(sql,args=()):return [dict(r) for r in db.execute(sql,args)]
r={'directory':str(OUT),'diagnostics':query('select * from DIAGNOSTIC_EVENT')}
zones=query("select start,end,globalTid,coalesce(n.text,s.value) label from NVTX_EVENTS n left join StringIds s on s.id=n.textId where coalesce(n.text,s.value) like 'SV04%' and end is not null order by start")
r['zones']=zones
window=next(z for z in zones if z['label']=='SV04_PROFILE');tid=window['globalTid'];lo,hi=window['start'],window['end']
r['main_tid']=tid;r['window_s']=(hi-lo)/1e9
r['thread_names']=query('select t.globalTid,s.value name from ThreadNames t join StringIds s on t.nameId=s.id where t.globalTid=?',(tid,))
work=[]
for table in ('VULKAN_WORKLOAD','CUPTI_ACTIVITY_KIND_KERNEL','CUPTI_ACTIVITY_KIND_MEMCPY'):
    rows=query('select start,end from '+table+' where end>? and start<? order by start',(lo,hi))
    work += [(max(lo,v['start']),min(hi,v['end'])) for v in rows]
def merge(rows):
    merged=[]
    for a,b in sorted(rows):
        if b<=a:continue
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    return merged
work=merge(work)
sched=query('select start,isSchedIn,threadState,threadBlock from SCHED_EVENTS where globalTid=? order by start',(tid,))
active=merge([(a['start'],b['start']) for a,b in zip(sched,sched[1:]) if a['isSchedIn']])
def duration(intervals,a,b):return sum(max(0,min(y,b)-max(x,a)) for x,y in intervals)/1e9
def longest_idle(intervals,a,b):
    last=a;largest=0
    for x,y in intervals:
        if y<a or x>b:continue
        largest=max(largest,max(0,x-last));last=max(last,y)
    return max(largest,b-last)/1e9
r['ranges']=[]
for z in zones:
    if '_initialize_async' not in z['label'] and not z['label'].startswith('SV04 step_async'):continue
    a,b=z['start'],z['end'];seconds=(b-a)/1e9
    v={**z,'duration_s':seconds,'main_scheduled_s':duration(active,a,b),'gpu_union_s':duration(work,a,b),
       'gpu_longest_no_recorded_work_s':longest_idle(work,a,b)}
    v['cpu_samples']=db.execute('select count(*) from COMPOSITE_EVENTS where globalTid=? and start>=? and start<?',(tid,a,b)).fetchone()[0]
    for name,sql in (
      ('leaf_hotspots',"select s.value symbol,m.value module,c.unresolved,count(*) samples from COMPOSITE_EVENTS e join SAMPLING_CALLCHAINS c on c.id=e.id left join StringIds s on s.id=c.symbol left join StringIds m on m.id=c.module where e.globalTid=? and e.start>=? and e.start<? and c.stackDepth=0 group by c.symbol,c.module,c.unresolved order by samples desc limit 15"),
      ('inclusive_modules',"select m.value module,count(distinct e.id) samples from COMPOSITE_EVENTS e join SAMPLING_CALLCHAINS c on c.id=e.id left join StringIds m on m.id=c.module where e.globalTid=? and e.start>=? and e.start<? group by c.module order by samples desc limit 15"),
      ('vulkan_api',"select s.value name,count(*) calls,sum(v.end-v.start)/1e9 total_s,max(v.end-v.start)/1e9 max_s from VULKAN_API v join StringIds s on s.id=v.nameId where v.globalTid=? and v.start>=? and v.start<? group by name order by total_s desc limit 10")):
        v[name]=query(sql,(tid,a,b))
    v['vulkan_allocation_counts']={name:db.execute(
        'select count(*) from VULKAN_API v join StringIds s on s.id=v.nameId where v.globalTid=? and v.start>=? and v.start<? and s.value=?',
        (tid,a,b,name)).fetchone()[0] for name in ('vkAllocateMemory','vkFreeMemory','vkGetMemoryFdKHR')}
    r['ranges'].append(v)
r['window_main_scheduled_s']=duration(active,lo,hi);r['window_gpu_union_s']=duration(work,lo,hi)
r['bins']=[{'offset_s':(a-lo)/1e9,'wall_s':min(.2,(hi-a)/1e9),'gpu_union_s':duration(work,a,min(a+200_000_000,hi)),
            'main_scheduled_s':duration(active,a,min(a+200_000_000,hi))} for a in range(lo,hi,200_000_000)]
r['leaf_sample_preview']=query('select e.id,e.start,c.stackDepth,s.value symbol,m.value module,c.unresolved from COMPOSITE_EVENTS e join SAMPLING_CALLCHAINS c on e.id=c.id left join StringIds s on c.symbol=s.id left join StringIds m on c.module=m.id where e.globalTid=? limit 15',(tid,))
tables={x['name'] for x in query("select name from sqlite_master where type='table'")}
if 'OSRT_API' in tables:
    for v in r['ranges']:
        v['osrt_api']=query("select s.value name,count(*) calls,sum(o.end-o.start)/1e9 inclusive_api_s,max(o.end-o.start)/1e9 max_s from OSRT_API o join StringIds s on s.id=o.nameId where o.globalTid=? and o.start>=? and o.start<? group by name order by inclusive_api_s desc limit 15",(tid,v['start'],v['end']))
for v in r['ranges']:
    v['cuda_api']=query("select s.value name,count(*) calls,sum(o.end-o.start)/1e9 inclusive_api_s,max(o.end-o.start)/1e9 max_s from CUPTI_ACTIVITY_KIND_RUNTIME o join StringIds s on s.id=o.nameId where o.globalTid=? and o.start>=? and o.start<? group by name order by inclusive_api_s desc limit 15",(tid,v['start'],v['end']))
db.close()
print(json.dumps({'encoding':'gzip-base64-json','data':base64.b64encode(gzip.compress(json.dumps(r).encode())).decode()}))
