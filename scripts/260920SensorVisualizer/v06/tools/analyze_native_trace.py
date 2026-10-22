"""Correlate NVTX scopes with CUDA, Vulkan and measured main-thread scheduling."""
import json,sqlite3
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');track=json.loads((root/'reports/latest_native_trace.json').read_text());out=Path(track['directory'])
db=sqlite3.connect('file:'+str(out/'native.sqlite')+'?mode=ro',uri=True)
ranges=db.execute("SELECT n.start,n.end,COALESCE(n.text,s.value),n.globalTid FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id WHERE COALESCE(n.text,s.value) LIKE 'SV06%' AND n.end IS NOT NULL").fetchall()
root_range=next(r for r in ranges if r[2]=='SV06_PROFILE');tid=root_range[3]
def union(intervals):
    intervals=sorted(intervals);total=0;last=None
    for a,b in intervals:
        if last is None:last=[a,b]
        elif a<=last[1]:last[1]=max(b,last[1])
        else:total+=last[1]-last[0];last=[a,b]
    return total+(last[1]-last[0] if last else 0)
def gpu_intervals(table,a,b):
    return [(max(a,s),min(b,e)) for s,e in db.execute('SELECT start,end FROM '+table+' WHERE start<? AND end>?',(b,a))]
def api(table,a,b,limit=15):
    rows=db.execute('SELECT s.value,count(*),sum(min(r.end,?)-max(r.start,?))/1e9,max(r.end-r.start)/1e6 FROM '+table+' r JOIN StringIds s ON r.nameId=s.id WHERE r.start<? AND r.end>? GROUP BY s.value ORDER BY sum(min(r.end,?)-max(r.start,?)) DESC LIMIT ?', (b,a,b,a,b,a,limit)).fetchall()
    return [{'api':n,'calls':c,'inclusive_wall_s':w,'max_ms':m} for n,c,w,m in rows]
sched=db.execute('SELECT start,isSchedIn FROM SCHED_EVENTS WHERE globalTid=? ORDER BY start',(tid,)).fetchall()
run=[];entered=None
for t,inside in sched:
    if inside:entered=t
    elif entered is not None:run.append((entered,t));entered=None
result={'trace':str(out/'native.nsys-rep'),'sqlite':str(out/'native.sqlite'),
        'limits':'Single instrumented group, including profiler overhead. CUDA API spans include waits; Vulkan batch intervals are not SM occupancy. Synchronous NVTX host scope across await includes other callbacks.',
        'stages':{}}
selected=[root_range]+sorted([r for r in ranges if r[2].startswith('SV06 render_wait')],key=lambda r:r[0])
for i,(a,b,name,_) in enumerate(selected):
    cuda=[]
    for table in ('CUPTI_ACTIVITY_KIND_KERNEL','CUPTI_ACTIVITY_KIND_MEMCPY','CUPTI_ACTIVITY_KIND_MEMSET'):cuda+=gpu_intervals(table,a,b)
    vk=gpu_intervals('VULKAN_WORKLOAD',a,b)
    main=[(max(a,s),min(b,e)) for s,e in run if s<b and e>a]
    copies=db.execute('SELECT copyKind,count(*),sum(bytes),sum(end-start)/1e9 FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE start>=? AND end<=? GROUP BY copyKind',(a,b)).fetchall()
    result['stages']['root' if i==0 else 'render_'+str(i)]={'label':name,'wall_s':(b-a)/1e9,
        'main_thread_running_s':union(main)/1e9,'cuda_union_s':union(cuda)/1e9,'vulkan_batch_union_s':union(vk)/1e9,
        'gpu_union_s':union(cuda+vk)/1e9,'cuda_runtime':api('CUPTI_ACTIVITY_KIND_RUNTIME',a,b),
        'vulkan_api':api('VULKAN_API',a,b),'main_os_waits':db.execute('SELECT s.value,count(*),sum(r.end-r.start)/1e9 FROM OSRT_API r JOIN StringIds s ON s.id=r.nameId WHERE r.globalTid=? AND r.start>=? AND r.end<=? GROUP BY s.value ORDER BY sum(r.end-r.start) DESC LIMIT 10',(tid,a,b)).fetchall(),
        'cuda_copies_by_kind':copies}
result['producer_interfaces']=[]
for f in (out/'captures/runs').glob('*/diagnostics/events_isaac_*.jsonl'):
    for line in f.read_text().splitlines():
        row=json.loads(line)
        if row['event']=='producer_array_interface':result['producer_interfaces'].append({k:row[k] for k in ('sensor_id','type','producer_device','shape','transfer_interface','ownership')})
result['own_copy_spans']={prefix:{'calls':sum(r[2].startswith('SV06 '+prefix) for r in ranges),
    'wall_s':sum(r[1]-r[0] for r in ranges if r[2].startswith('SV06 '+prefix))/1e9} for prefix in ('host_materialize','cpu_owned_copy')}
result['devices']=[dict(zip(('id','name','bus','uuid'),r)) for r in db.execute('SELECT id,name,busLocation,uuid FROM TARGET_INFO_GPU')]
db.close();(root/'reports/native_trace_analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
