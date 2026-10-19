"""Run identical isolated cases; own only child PIDs; measurements exclude GUI network."""
import argparse,importlib,json,math,os,signal,subprocess,sys,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('spec');args=parser.parse_args();spec=json.loads(Path(args.spec).read_text())
PROJECT=ROOT.parent/spec['version'];OUT=Path(spec['directory']);OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(PROJECT));pkg='sensor_visualizer_'+spec['version']
request=importlib.import_module(pkg+'.control_ipc').request
TrajectoryRecorder=importlib.import_module(pkg+'.trajectory').TrajectoryRecorder
load_job=importlib.import_module(pkg+'.contracts').load_job
owned=[];halt=threading.Event();phase={'case':'initializing'};resource_file=(OUT/'resources.jsonl').open('a')
def save(name,value):
    p=OUT/name;temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(p)
def start(command,name,env=None):
    log=(OUT/(name+'.log')).open('ab');p=subprocess.Popen(command,cwd=PROJECT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
    tick=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    owned.append(p);save(name+'_process.json',{'pid':p.pid,'start_ticks':tick,'command':command});return p
def stop(p):
    if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=20)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
def sampler():
    previous={};ticks=os.sysconf('SC_CLK_TCK')
    while not halt.is_set():
        begin=time.monotonic_ns();row={'monotonic_ns':begin,**phase,'processes':{}}
        status_path=OUT/(phase['case']+'_status.json')
        if status_path.exists():
            try:
                current=json.loads(status_path.read_text());row.update(capture_phase=current.get('state'),group_id=current.get('group_id',current.get('groups')))
            except (OSError,json.JSONDecodeError):pass
        for p in list(owned):
            if p.poll() is not None:continue
            try:
                fields=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split();cpu=(int(fields[11])+int(fields[12]))/ticks
                old=previous.get(p.pid);previous[p.pid]=(begin,cpu)
                status=Path('/proc',str(p.pid),'status').read_text().splitlines()
                row['processes'][str(p.pid)]={'cpu_cores':(cpu-old[1])/((begin-old[0])/1e9) if old else None,
                    'rss_kib':next(int(x.split()[1]) for x in status if x.startswith('VmRSS:')),
                    'wchan':Path('/proc',str(p.pid),'wchan').read_text().strip(),
                    'voluntary_context_switches':next(int(x.split()[1]) for x in status if x.startswith('voluntary_ctxt_switches:')),
                    'involuntary_context_switches':next(int(x.split()[1]) for x in status if x.startswith('nonvoluntary_ctxt_switches:'))}
            except (OSError,ValueError,StopIteration):pass
        try:
            smi=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2)
            row['whole_gpu']=smi.stdout.strip();row['query_ms']=(time.monotonic_ns()-begin)/1e6
        except Exception as exc:row['gpu_error']=str(exc)
        resource_file.write(json.dumps(row)+'\n');resource_file.flush();halt.wait(1)
def state():return request(OUT/'engine.sock',{'action':'status'})
def command(action,payload=None):
    cid=uuid.uuid4().hex;request(OUT/'engine.sock',{'action':action,'payload':payload or {},'command_id':cid})
    end=time.monotonic()+5
    while time.monotonic()<end:
        s=state();receipt=next((x for x in s.get('receipts',[]) if x['command_id']==cid),None)
        if receipt:
            assert receipt['state']=='applied',receipt
            return s,(receipt['completed_ns']-receipt['accepted_ns'])/1e6
        time.sleep(.01)
    raise TimeoutError(action)
def quantiles(values):
    if not values:return None
    a=sorted(values);return {'n':len(a),'p50':a[int(.5*(len(a)-1))],'p95':a[int(.95*(len(a)-1))],'p99':a[int(.99*(len(a)-1))],'max':a[-1]}
def measure(label,seconds=None,child=None):
    phase.update(case=label,capture_phase='none',group_id=None);begin=time.monotonic();previous_updates=state()['statistics']['updates'];lat=[];gaps=[];cpu=[]
    rows=(OUT/(label+'_commands.jsonl')).open('w');initial_slow=state()['statistics']['slow_updates']
    while (child is not None and child.poll() is None) or (child is None and time.monotonic()-begin<seconds):
        cycle=time.monotonic();keys=['W','Q','U'] if int(cycle-begin)%5<3 else []
        s,elapsed=command('keys',{'source':'web:performance-suite','keys':keys});lat.append(elapsed)
        stats=s['statistics'];count=max(0,stats['updates']-previous_updates);previous_updates=stats['updates']
        gaps.extend(stats['frame_gap_samples'][-count:] if count else []);cpu.extend(stats['owner_ms_samples'][-count:] if count else [])
        status_path=OUT/(label+'_status.json')
        if status_path.exists():
            try:
                capture=json.loads(status_path.read_text());phase.update(capture_phase=capture.get('state'),group_id=capture.get('group_id',capture.get('groups')))
            except (OSError,json.JSONDecodeError):pass
        rows.write(json.dumps({'monotonic_ns':time.monotonic_ns(),'applied_ms':elapsed,'update_count':stats['updates'],**phase})+'\n')
        if time.monotonic()-begin>spec.get('timeout_s',420):raise TimeoutError(label)
        time.sleep(max(0,.1-(time.monotonic()-cycle)))
    rows.close();command('keys',{'source':'web:performance-suite','keys':[]})
    result={'wall_s':time.monotonic()-begin,'applied_ms':quantiles(lat),'frame_gap_ms':quantiles(gaps),'owner_ms':quantiles(cpu),
        'frame_gaps_over_ms':{str(x):sum(v>x for v in gaps) for x in (50,100,250,500)},'slow_updates':s['statistics']['slow_updates']-initial_slow}
    save(label+'_metrics.json',result);return result
def capture(label,trajectory):
    job=load_job(overrides={'groups':spec.get('groups',8),'output_directory':str(OUT/'captures'),
        'diagnostics':{'level':'diagnostic','export_trace_on_stop':True},
        'replay':{'mode':'offline','trajectory':str(trajectory),'socket':str(OUT/'engine.sock'),
                  'control_path':str(OUT/(label+'_control.json')),'status_path':str(OUT/(label+'_status.json'))}})
    if spec.get('job_overrides'):job=importlib.import_module(pkg+'.contracts').merge(job,spec['job_overrides'])
    save(label+'_job.json',job);save(label+'_control.json',{'action':'run'})
    return start(['/usr/bin/python3',str(PROJECT/'run_capture.py'),'--job',str(OUT/(label+'_job.json')),'--entry',str(PROJECT/'kit_replay_entry.py')],label)
def interrupted(*_):raise KeyboardInterrupt('Owned experiment interrupted')
signal.signal(signal.SIGTERM,interrupted)
thread=threading.Thread(target=sampler,daemon=True);thread.start();result={}
try:
    phase['case']='owner_start';env=os.environ.copy();env.update(SV_BENCH_ROOT=str(PROJECT),SV_BENCH_DIR=str(OUT))
    displays=list(Path('/tmp/.X11-unix').glob('X*'));assert len(displays)==1;env['DISPLAY']=':'+displays[0].name[1:]
    owner=start(['/usr/bin/python3',str(PROJECT/'run_capture.py'),'--gui','--entry',str(ROOT/'tools/benchmark_entry.py')],'owner',env)
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        if owner.poll() is not None:raise RuntimeError('Owner exited; inspect owner.log')
        try:
            s=state()
            if s['phase']=='interactive_ready':break
        except (OSError,EOFError):pass
        time.sleep(.5)
    else:raise TimeoutError('owner initialize')
    time.sleep(5)
    if spec.get('trajectory'):trajectory=Path(spec['trajectory'])
    else:
        trajectory=OUT/'input_trajectory';recorder=TrajectoryRecorder(trajectory,s['metadata'])
        for i in range(61):
            row=json.loads(json.dumps(s['state']));row.update(t_sim_s=i*.1,snapshot_id=uuid.uuid4().hex,state_revision=i,transition_kind='continuous')
            row['joints_deg']={n:v+3*math.sin(i*.1) for n,v in row['joints_deg'].items()};recorder.append(row)
        recorder.close()
    save('input.json',{'trajectory':str(trajectory),'version':spec['version'],'groups':spec.get('groups',8)})
    command('play');result['interactive_only']=measure('interactive_only',seconds=spec.get('interactive_seconds',45))
    child=capture('concurrent',trajectory);result['concurrent']=measure('concurrent',child=child);assert child.returncode==0,'Concurrent capture failed'
    phase.update(case='owner_close',capture_phase='none',group_id=None)
    try:request(OUT/'engine.sock',{'action':'close'})
    except OSError:pass
    try:owner.wait(timeout=25)
    except subprocess.TimeoutExpired:stop(owner)
    phase.update(case='capture_only',group_id=None);child=capture('capture_only',trajectory)
    try:child.wait(timeout=spec.get('timeout_s',420))
    except subprocess.TimeoutExpired:raise TimeoutError('capture_only')
    assert child.returncode==0,'Capture-only failed'
    for label in ('concurrent','capture_only'):
        final=json.loads((OUT/(label+'_status.json')).read_text());assert final['state']=='finished' and final['groups']==spec.get('groups',8),final
        result.setdefault(label,{})['capture']=final
    result['capture_only']={'capture':json.loads((OUT/'capture_only_status.json').read_text())}
    result.update(passed=True,trajectory=str(trajectory),version=spec['version']);save('result.json',result)
except BaseException:
    import traceback;result.update(passed=False,error=traceback.format_exc());save('result.json',result);raise
finally:
    for p in reversed(owned):stop(p)
    halt.set();thread.join(timeout=4);resource_file.close()
