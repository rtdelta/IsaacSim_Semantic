"""Stdlib evidence joiner. Keep inclusive API time, GPU activity and counters separate."""
import collections,csv,hashlib,json,math,re,sqlite3,statistics
from pathlib import Path

def interval_union(intervals):
    total=0;last=None
    for a,b in sorted((a,b) for a,b in intervals if b>a):
        if last is None:last=[a,b]
        elif a<=last[1]:last[1]=max(last[1],b)
        else:total+=last[1]-last[0];last=[a,b]
    return total+(last[1]-last[0] if last else 0)

def clipped(intervals,start,end):return [(max(start,a),min(end,b)) for a,b in intervals if b>start and a<end]
def quantile(values,q):
    if not values:return None
    s=sorted(values);return s[max(0,min(len(s)-1,math.ceil(len(s)*q)-1))]
def stats(values):
    v=[float(x) for x in values if x is not None and math.isfinite(float(x))]
    return {'samples':len(v),'min':min(v) if v else None,'max':max(v) if v else None,
            'mean':statistics.mean(v) if v else None,'p50':quantile(v,.5),'p95':quantile(v,.95),
            'p99':quantile(v,.99),'quantile_method':'nearest_rank; small samples do not establish tail stability'}

def load_rows(directory):
    rows=[]
    for path in (Path(directory)/'captures/runs').glob('*/diagnostics/events_*.jsonl'):
        with path.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():rows.append(json.loads(line))
    return sorted(rows,key=lambda r:(r['monotonic_ns'],r['pid'],r['event_seq']))

def align_anchors(anchors):
    offsets=[host-native for native,host in anchors]
    if not offsets:return {'available':False,'reason':'No exact host_ns NVTX anchor'}
    median=round(statistics.median(offsets))
    return {'available':True,'offset_ns':median,'anchors':len(offsets),
            'residual_max_abs_ns':max(abs(x-median) for x in offsets),
            'method':'same-process SL06_SYNC encoded monotonic_ns minus native NVTX start; no wall clock conversion',
            'limit':'anchor call delay and profiler instrumentation contribute alignment uncertainty'}

def identifier(name):
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Unexpected SQL identifier')
    return '"'+name+'"'

def native_report(path,scopes):
    if not Path(path).is_file():return {'available':False,'reason':'Ordinary unprofiled run'}
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    schema={r[0]:[c[1] for c in db.execute('PRAGMA table_info('+identifier(r[0])+')')]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',r[0])}
    out={'available':True,'schema':schema,'stages':{},'gpu_metrics':{},'limitations':[
        'CUDA/Vulkan API inclusive durations contain waits and overlap; do not sum as exclusive cost.',
        'Vulkan batch + CUDA active interval union is observed GPU activity, not core utilization.',
        'GPU metrics cover the entire device; profiler runs are excluded from throughput comparisons.']}
    ranges=[]
    if 'NVTX_EVENTS' in schema:
        query='SELECT n.start,n.end,COALESCE(n.text,s.value) label,n.globalTid FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id'
        ranges=[dict(r) for r in db.execute(query)]
    anchors=[]
    for r in ranges:
        m=re.match(r'SL06_SYNC host_ns=(\d+)',r['label'] or '')
        if m:anchors.append((r['start'],int(m.group(1))))
    alignment=align_anchors(anchors);out['clock_alignment']=alignment
    if 'CUPTI_ACTIVITY_KIND_RUNTIME' in schema and 'callchainId' in schema['CUPTI_ACTIVITY_KIND_RUNTIME']:
        total,backtraced=db.execute('SELECT count(*),count(callchainId) FROM CUPTI_ACTIVITY_KIND_RUNTIME').fetchone()
        out['cuda_api_backtrace_coverage']={'api_rows':total,'rows_with_callchain':backtraced,
            'available':bool(backtraced),'limit':'A requested CLI option does not prove collected API backtraces; CPU sampling ancestry is separate evidence.'}
    gpu=[]
    for table in ('VULKAN_WORKLOAD','CUPTI_ACTIVITY_KIND_KERNEL','CUPTI_ACTIVITY_KIND_MEMCPY','CUPTI_ACTIVITY_KIND_MEMSET'):
        if table in schema and {'start','end'}.issubset(schema[table]):
            gpu.extend((r[0],r[1],table) for r in db.execute('SELECT start,end FROM '+identifier(table)) if r[1]>r[0])
    prefixes=('SV06 lab.SceneStepper.','SV06 render_wait ','SV06 lab.SensorDrivers.warm_cameras ',
              'SV06 lab.SensorDrivers.acquire ','SV06 lab.SensorDrivers.detach ','SV06 lab.SensorDrivers.destroy ')
    native_scopes=[r for r in ranges if r['end'] and (r['label']=='SL06_WINDOW' or (r['label'] or '').startswith(prefixes))]
    schedules=collections.defaultdict(list)
    if 'SCHED_EVENTS' in schema:
        entered={}
        for r in db.execute('SELECT start,isSchedIn,globalTid FROM SCHED_EVENTS ORDER BY start'):
            t,inside,tid=r
            if inside:entered[tid]=t
            elif tid in entered:schedules[tid].append((entered.pop(tid),t))
    for scope in native_scopes:
        a,b=scope['start'],scope['end'];key=str(a)+' '+scope['label']
        v={'start_native_ns':a,'end_native_ns':b,'wall_s':(b-a)/1e9,'label':scope['label'],
           'gpu_activity_union_s':interval_union(clipped([(s,e) for s,e,_ in gpu],a,b))/1e9,
           'main_thread_scheduled_s':interval_union(clipped(schedules[scope['globalTid']],a,b))/1e9,
           'activity_by_engine':{},'apis':{}}
        for engine in set(t for _,_,t in gpu):
            v['activity_by_engine'][engine]=interval_union(clipped([(s,e) for s,e,t in gpu if t==engine],a,b))/1e9
        for table in ('CUPTI_ACTIVITY_KIND_RUNTIME','CUPTI_ACTIVITY_KIND_DRIVER','VULKAN_API','OSRT_API'):
            if table not in schema or not {'start','end','nameId'}.issubset(schema[table]):continue
            q='''SELECT s.value name,count(*) calls,sum(min(r.end,?)-max(r.start,?)) inclusive_ns,
                     max(r.end-r.start) max_ns FROM TABLE r JOIN StringIds s ON s.id=r.nameId
                     WHERE r.start<? AND r.end>? GROUP BY s.value ORDER BY inclusive_ns DESC LIMIT 30'''.replace('TABLE',identifier(table))
            parameters=(b,a,b,a)
            if table=='OSRT_API' and 'globalTid' in schema[table]:
                q=q.replace('GROUP BY','AND r.globalTid=? GROUP BY');parameters+=(scope['globalTid'],)
            v['apis'][table]=[dict(r) for r in db.execute(q,parameters)]
        if 'CUPTI_ACTIVITY_KIND_RUNTIME' in schema:
            v['cuda_module_lifecycle']=[dict(r) for r in db.execute('''SELECT s.value name,count(*) calls,
                sum(min(r.end,?)-max(r.start,?)) inclusive_ns FROM CUPTI_ACTIVITY_KIND_RUNTIME r
                JOIN StringIds s ON s.id=r.nameId WHERE r.start<? AND r.end>?
                AND (s.value LIKE 'cuModule%' OR s.value LIKE 'cuLink%') GROUP BY s.value''',(b,a,b,a))]
        v['api_scope']='OSRT restricted to scope start thread; CUDA/Vulkan across traced process tree; inclusive calls may overlap'
        if 'COMPOSITE_EVENTS' in schema and 'SAMPLING_CALLCHAINS' in schema:
            query='''SELECT m.value module,count(*) samples FROM COMPOSITE_EVENTS e
             JOIN SAMPLING_CALLCHAINS c ON c.id=e.id LEFT JOIN StringIds m ON m.id=c.module
             WHERE c.stackDepth=0 AND e.globalTid=? AND e.start>=? AND e.start<=?
             GROUP BY module ORDER BY samples DESC LIMIT 20'''
            v['cpu_leaf_module_samples']=[dict(r) for r in db.execute(query,(scope['globalTid'],a,b))]
            v['cpu_sample_limit']='Sampled leaf-module counts on scope start thread; stripped symbols do not identify exact function or algorithm.'
            if 'CUPTI_ACTIVITY_KIND_RUNTIME' in schema:
                # Bisect in memory: exact same-thread sample membership in an
                # observed API interval. Avoid a costly SQL interval cross join.
                import bisect
                sample_times=[x[0] for x in db.execute('SELECT start FROM COMPOSITE_EVENTS WHERE globalTid=? AND start BETWEEN ? AND ? ORDER BY start',(scope['globalTid'],a,b))]
                membership=collections.Counter()
                for call in db.execute('''SELECT r.start,r.end,s.value FROM CUPTI_ACTIVITY_KIND_RUNTIME r
                    JOIN StringIds s ON s.id=r.nameId WHERE r.globalTid=? AND r.start<? AND r.end>?''',(scope['globalTid'],b,a)):
                    count=bisect.bisect_right(sample_times,min(b,call[1]))-bisect.bisect_left(sample_times,max(a,call[0]))
                    if count:membership[call[2]]+=count
                v['main_thread_cpu_samples_inside_cuda_api']=dict(membership.most_common(20))
                v['sample_membership_limit']='Same-thread sample timestamp inside inclusive API interval; nested APIs can overlap. Not API-exclusive time or invocation counts.'
        if 'CUPTI_ACTIVITY_KIND_KERNEL' in schema and 'demangledName' in schema['CUPTI_ACTIVITY_KIND_KERNEL']:
            v['cuda_kernel_hotspots']=[dict(r) for r in db.execute('''SELECT s.value name,count(*) calls,
             sum(min(k.end,?)-max(k.start,?)) gpu_duration_sum_ns FROM CUPTI_ACTIVITY_KIND_KERNEL k
             JOIN StringIds s ON s.id=k.demangledName WHERE k.start<? AND k.end>?
             GROUP BY s.value ORDER BY gpu_duration_sum_ns DESC LIMIT 10''',(b,a,b,a))]
        out['stages'][key]=v
    window=next((r for r in ranges if r['label']=='SL06_WINDOW' and r['end']),None)
    if window and 'CUDA_GPU_MEMORY_USAGE_EVENTS' in schema:
        out['cuda_memory_window']=[dict(r) for r in db.execute('''SELECT memoryOperationType,memKind,
            count(*) events,sum(bytes) bytes_sum FROM CUDA_GPU_MEMORY_USAGE_EVENTS
            WHERE start BETWEEN ? AND ? GROUP BY memoryOperationType,memKind''',(window['start'],window['end']))]
        out['cuda_memory_window_limit']='Clipped window may begin/end with live allocations; counts or byte differences do not establish a leak or pure allocation cost.'
        ledger=Path(path).parent/'native_memory_ledger.csv'
        with ledger.open('w',newline='',encoding='utf-8-sig') as f:
            columns=['start_native_ns','device','context','resource_fingerprint','bytes','memory_kind','operation','correlation_id']
            writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
            for t,device,context,address,size,kind,operation,correlation in db.execute('''SELECT start,deviceId,contextId,address,bytes,memKind,memoryOperationType,correlationId
                FROM CUDA_GPU_MEMORY_USAGE_EVENTS WHERE start BETWEEN ? AND ? ORDER BY start''',(window['start'],window['end'])):
                writer.writerow(dict(zip(columns,[t,device,context,hashlib.sha256(str(address).encode()).hexdigest()[:16],size,kind,
                    'allocation' if operation==0 else 'deallocation' if operation==1 else str(operation),correlation])))
    # Metric catalog is explicit, so unsupported metrics cannot appear as zero.
    catalog=[]
    for table,columns in schema.items():
        if 'METRIC' in table and table!='GPU_METRICS' and ('metricName' in columns or 'name' in columns):
            catalog.extend({'table':table,**dict(r)} for r in db.execute('SELECT * FROM '+identifier(table)))
    out['metric_catalog']=catalog
    if 'GPU_METRICS' in schema:
        out['gpu_metric_schema']=schema['GPU_METRICS'];out['gpu_metric_row_count']=db.execute('SELECT count(*) FROM GPU_METRICS').fetchone()[0]
        columns=schema['GPU_METRICS']
        if {'timestamp','metricId','value'}.issubset(columns):
            type_col='typeId' if 'typeId' in columns else None
            grouping=('typeId,' if type_col else '')+'metricId'
            ids=db.execute('SELECT DISTINCT '+grouping+' FROM GPU_METRICS').fetchall()
            for ids_row in ids:
                ids_value=tuple(ids_row);where=('typeId=? AND ' if type_col else '')+'metricId=?'
                samples=[tuple(r) for r in db.execute('SELECT timestamp,value FROM GPU_METRICS WHERE '+where+' ORDER BY timestamp',ids_value)]
                if window:samples=[(t,v) for t,v in samples if window['start']<=t<=window['end']]
                metric=next((c for c in catalog if c.get('metricId')==ids_value[-1] and (not type_col or c.get('typeId')==ids_value[0])),{})
                name=metric.get('metricName',metric.get('name','metric_'+str(ids_value)))
                gaps=[b[0]-a[0] for a,b in zip(samples,samples[1:])]
                nominal=statistics.median(gaps) if gaps else None
                large=sum(g for g in gaps if nominal and g>3*nominal)
                v={**stats([v for _,v in samples]),'identity':ids_value,'catalog':metric,
                   'median_sample_interval_ns':nominal,'large_gap_ns':large,
                   'coverage_limit':'No interpolation across gaps >3 median periods; summary mean is sample mean'}
                if '[MHz]' in name and (v['min'] is not None and (v['min']<0 or v['max']>10000)):
                    v['valid_for_interpretation']=False
                    v['anomaly']='Installed exporter value contradicts MHz label (raw Hz / signed overflow suspected, not silently converted). Use NVML clocks.'
                elif '[Threads/Warp]' in name and v['max'] is not None and v['max']>32:
                    v['valid_for_interpretation']=False
                    v['anomaly']='Value exceeds installed NVIDIA warp width 32 and contradicts Threads/Warp label. Raw count or exporter normalization issue; not silently reinterpreted.'
                elif '[GB/s]' in name and v['max'] is not None and v['max']>10000:
                    v['valid_for_interpretation']=False
                    v['anomaly']='PCIe bandwidth magnitude contradicts GB/s label. Raw bytes/second suspected; do not infer physical bandwidth from this value.'
                else:v['valid_for_interpretation']=True
                v['per_stage_samples']={key:stats([value for t,value in samples if stage['start_native_ns']<=t<=stage['end_native_ns']])
                                        for key,stage in out['stages'].items()}
                out['gpu_metrics'][name]=v
    else:out['gpu_metrics_unavailable']='GPU_METRICS table absent; check capture log / hardware counter permission'
    db.close();return out

def analyze(directory):
    directory=Path(directory);rows=load_rows(directory);ends=[r for r in rows if r['event']=='span_end']
    stage=collections.defaultdict(list)
    for row in ends:stage[row['name']].append(row)
    out={'directory':str(directory),'limits':[
        'Host wall and same-thread inclusive CPU spans across await include other callbacks; they are not exclusive function costs.',
        'NVML 1-second samples describe whole-device averages, not CUDA/RT/Tensor core occupancy.',
        'Dependency duration is inclusive scope, not a measured pure blocked interval. Native stacks needed for attribution.'],
        'host_stages':{name:{'wall_ms':stats([r['duration_ns']/1e6 for r in rr]),
            'inclusive_thread_cpu_ms':stats([r['thread_cpu_duration_ns']/1e6 for r in rr if r.get('thread_cpu_duration_ns') is not None])}
            for name,rr in stage.items()},'dependencies':[],'buffers':[],'event_counts':dict(collections.Counter(r['event'] for r in rows))}
    end_by_id={r['span_id']:r for r in ends}
    for row in rows:
        if row['event']=='lab_dependency':
            e=end_by_id.get(row['dependency_span_id'])
            out['dependencies'].append({**row,'inclusive_duration_ns':e.get('duration_ns') if e else None,
                                         'completion_status':e.get('status') if e else 'not_observed'})
        if row['event']=='lab_source_buffer':out['buffers'].append(row)
    out['buffer_contract']={'safe_cross_group_overlap':False,
        'reason':'SDK payload exposes device arrays but no retained lifetime or explicit Vulkan producer fence in callback interface.',
        'camera_devices':sorted(set(r['source_buffer']['device'] for r in out['buffers'] if (r.get('sensor_id') or '').startswith('cameras/'))),
        'lidar_devices':sorted(set(r['source_buffer']['device'] for r in out['buffers'] if (r.get('sensor_id') or '').startswith('lidars/'))),
        'distinct_buffer_fingerprints':len(set(r['source_buffer'].get('buffer_fingerprint',r['source_buffer'].get('pointer_token')) for r in out['buffers']
            if r['source_buffer'].get('buffer_fingerprint',r['source_buffer'].get('pointer_token'))))}
    out['profiler_trigger_costs']=[r for r in rows if r['event']=='lab_profile_window']
    out['native']=native_report(directory/'native.sqlite',ends)
    out['loaded_modules']=[r for r in rows if r['event']=='lab_module_mapping']
    resource=directory/'system_resources.jsonl'
    if resource.is_file():
        rr=[json.loads(l) for l in resource.read_text().splitlines() if l.strip()]
        out['nvml_summary']={k:stats([r.get('gpu',{}).get(k) for r in rr]) for k in
            ('gpu_percent','memory_busy_percent','memory_used_bytes','sm_clock_mhz','memory_clock_mhz','pcie_tx_kb_s','pcie_rx_kb_s')}
        process_samples=[]
        for old,new in zip(rr,rr[1:]):
            a,b=old.get('process'),new.get('process')
            if not a or not b or (a['pid'],a['start_ticks'])!=(b['pid'],b['start_ticks']):continue
            delta=new['host_monotonic_ns']-old['host_monotonic_ns']
            cores=((b['user_ticks']+b['system_ticks'])-(a['user_ticks']+a['system_ticks']))/b['clock_ticks_per_second']/(delta/1e9)
            process_samples.append({'start_ns':old['host_monotonic_ns'],'end_ns':new['host_monotonic_ns'],'cpu_cores':cores,
                'rss_bytes':b['rss_pages']*b['page_size']})
        out['coarse_resources_by_host_phase']={}
        for name,scopes in stage.items():
            if not name.startswith('lab.SceneStepper.') and name not in ('lab.SensorDrivers.warm_cameras',):continue
            ranges=[(r['start_ns'],r['start_ns']+r['duration_ns']) for r in scopes]
            samples=[r for r in rr if any(a<=r['host_monotonic_ns']<=b for a,b in ranges)]
            cpu=[r for r in process_samples if any(r['end_ns']>=a and r['start_ns']<=b for a,b in ranges)]
            out['coarse_resources_by_host_phase'][name]={
                'gpu_percent':stats([r.get('gpu',{}).get('gpu_percent') for r in samples]),
                'gpu_memory_bytes':stats([r.get('gpu',{}).get('memory_used_bytes') for r in samples]),
                'process_cpu_cores':stats([r['cpu_cores'] for r in cpu]),'process_rss_bytes':stats([r['rss_bytes'] for r in cpu]),
                'limit':'1-second device/CPU samples can straddle phases; short stages may have no samples. CPU cores=1 means one full core, not whole-host utilization.'}
    out['diagnostics_health']=[]
    for p in (directory/'captures/runs').glob('*/diagnostics/summary*.json'):
        r=json.loads(p.read_text());out['diagnostics_health'].append({'path':str(p),'state':r.get('state'),'dropped':r.get('telemetry_dropped'),'io_error':r.get('io_error')})
    (directory/'analysis.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    with (directory/'dependency_ledger.csv').open('w',newline='',encoding='utf-8-sig') as f:
        columns=['group_id','request_id','sensor_id','waiter','producer','resource','completion_signal','inclusive_duration_ns','completion_status']
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(out['dependencies'])
    with (directory/'resource_ledger.csv').open('w',newline='',encoding='utf-8-sig') as f:
        columns=['host_monotonic_ns','event','group_id','sensor_id','resource','operation','scope']
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader()
        for row in rows:
            if row['event']=='lab_source_buffer':
                w.writerow({'host_monotonic_ns':row.get('monotonic_ns',row.get('start_ns')),'event':row['event'],
                    'group_id':row.get('group_id'),'sensor_id':row.get('sensor_id'),
                    'resource':json.dumps(row.get('source_buffer',{})),'operation':'observe_callback_source',
                    'scope':'Metadata only; does not establish ownership or producer completion fence'})
            elif row['event']=='span_end' and any(k in row.get('name','') for k in ('ProductGate.','detach','destroy','copy_owned')):
                w.writerow({'host_monotonic_ns':row.get('start_ns'),'event':row['event'],
                    'group_id':row.get('group_id'),'sensor_id':row.get('sensor_id'),'resource':row.get('name'),
                    'operation':row.get('status'),'scope':'Host inclusive lifecycle scope; underlying native allocations remain in SQLite'})
    return out
