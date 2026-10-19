"""Launch existing Kit and standard rosbag2; supervision never handles sensor data."""
import argparse,hashlib,json,os,resource,signal,subprocess,threading,time,sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ISAAC=Path('/root/isaacsim')
NSYS=Path('/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys')

def write(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)

def engine_command(spec,out):
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
    env.update(RESOURCE_NAME='IsaacSim',ROS_DISTRO='jazzy',RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
       AMENT_PREFIX_PATH='/opt/ros/jazzy',ROS_DOMAIN_ID=str(spec['ros_domain_id']),ROS_LOCALHOST_ONLY='1',
       NATIVE_BASELINE_SPEC=str(out/'spec.json'),NATIVE_BASELINE_OUTPUT=str(out),PYTHONUNBUFFERED='1')
    paths=[str(p) for pattern in ('omni.sensors.nv.common-*/bin/checker_lib/bin','omni.sensors.nv.common-*/bin',
        'omni.sensors.nv.lidar-*/bin/model_plugins') for p in (ISAAC/'extscache').glob(pattern)]
    paths += [str(ISAAC/p) for p in ('exts/isaacsim.ros2.core/bin','kit/python/lib','kit',
        'kit/kernel/plugins','exts/isaacsim.ros2.core/jazzy/lib','kit/plugins/rtx')]
    env['LD_LIBRARY_PATH']=':'.join(paths+['/opt/ros/jazzy/lib'])
    args=[str(ISAAC/'kit/kit'),str(ISAAC/'apps/isaacsim.exp.full.kit'),'--allow-root','--no-window',
       '--/app/window/enabled=false','--/renderer/multiGpu/enabled=false',
       '--/persistent/rtx/modes/pt/enabled=true','--/persistent/rtx/modes/rt2/enabled=true',
       '--/persistent/app/newStage/defaultTemplate=empty','--/app/settings/persistent=false',
       '--/app/extensions/registryEnabled=false','--/app/extensions/syncRegistryOnStartup=false',
       '--/app/asyncRendering=false','--/exts/isaacsim.core.throttling/enable_async=false',
       '--/app/renderer/skipWhileMinimized=false','--/renderer/raytracingMotion/enabled=false',
       '--/rtx/hydra/supportMultiTickRate='+str(spec['multi_tick']).lower(),
       '--/rtx/rendering/perSensorTickTlas='+str(spec['multi_tick']).lower(),
       '--/persistent/app/usd/muteUsdDiagnostics=false','--/app/fastShutdown=true',
       '--/app/file/ignoreUnsavedOnExit=true',
       '--/exts/omni.services.transport.server.http/http/enabled=false',
       '--/exts/omni.services.transport.server.http/https/enabled=false',
       '--/crashreporter/enabled=false','--/crashreporter/skipOldDumpUpload=true','--/crashreporter/url=',
       '--/telemetry/enableAnonymousData=false','--enable','isaacsim.sensors.rtx.nodes',
       '--enable','isaacsim.ros2.bridge','--exec',str(ROOT/'kit_entry.py')]
    if spec['trace']:
        env['NSYS_NVTX_PROFILER_REGISTER_ONLY']='0'
        args=[str(NSYS),'profile','--trace=vulkan,cuda,nvtx,osrt','--sample=process-tree',
            '--cpuctxsw=process-tree','--backtrace=lbr','--vulkan-gpu-workload=batch',
            '--capture-range=nvtx','--nvtx-capture=NATIVE_CAPTURE_WINDOW','--capture-range-end=stop',
            '--gpu-metrics-devices=0','--gpu-metrics-set=ad10x','--gpu-metrics-frequency=1000',
            '--export=sqlite','--output='+str(out/'native'),*args]
    return args,env

def ros_command(args):
    # Argument vector passed through shell positional parameters, never interpolated.
    return ['bash','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','native-ros',*args]

def proc_sample(pid):
    p=Path('/proc')/str(pid)
    try:
        s=(p/'stat').read_text().rsplit(')',1)[1].split()
        threads={}
        for t in (p/'task').iterdir():
            try:
                x=(t/'stat').read_text().rsplit(')',1)[1].split()
                threads[t.name]={'user_ticks':int(x[11]),'system_ticks':int(x[12]),'cpu':int(x[36])}
            except (OSError,ValueError):pass
        return {'pid':pid,'start_ticks':int(s[19]),'user_ticks':int(s[11]),'system_ticks':int(s[12]),
            'rss_bytes':int(s[21])*os.sysconf('SC_PAGE_SIZE'),'ticks_per_second':os.sysconf('SC_CLK_TCK'),'threads':threads}
    except (OSError,ValueError):return None

def sample(out,stop,recorder):
    fields='utilization.gpu,utilization.memory,memory.used,memory.total,clocks.sm,clocks.mem,power.draw'
    with (out/'resources.jsonl').open('x') as f:
        while not stop.is_set():
            row={'host_monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns(),'gpu_scope':'whole device'}
            try:
                r=subprocess.run(['nvidia-smi','--query-gpu='+fields,'--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
                v=r.stdout.strip().split(', ')
                row['gpu']={n:float(x) if x not in ('[N/A]','N/A') else None for n,x in zip(fields.split(','),v)}
                pid=int((out/'kit.pid').read_text());row['kit']=proc_sample(pid)
            except (OSError,ValueError,subprocess.TimeoutExpired) as exc:row['sample_error']=str(exc)
            if recorder:row['recorder']=proc_sample(recorder.pid)
            f.write(json.dumps(row)+'\n');f.flush();stop.wait(1)

def close_child(p,sig,timeout):
    if p is None or p.poll() is not None:return
    os.killpg(p.pid,sig)
    try:p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)

def run(spec,directory):
    if os.name!='posix':raise RuntimeError('Run on the Linux Isaac instance')
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if b'/kit/kit' in p.read_bytes().split(b'\0')[0]:raise RuntimeError('Existing Isaac process detected; it was not stopped')
        except OSError:pass
    out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=False)
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(spec['scene'])]}
    write(out/'spec.json',spec);write(out/'runner.pid',{'pid':os.getpid()})
    source_files=[ROOT/'run.py',ROOT/'kit_entry.py',ROOT/'experiment.py',ROOT/'continuous.py',ROOT/'tools/validate_bag.py',ROOT/'tools/validate_groups.py',ROOT/'config/baseline.json']
    write(out/'source_manifest.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files})
    args,env=engine_command(spec,out)
    result={'state':'running','output':str(out),'started_utc_ns':time.time_ns(),'mode':spec['mode'],
       'trace':spec['trace'],'recorder_exit':None,'engine_exit':None}
    recorder=engine=None;stop=threading.Event();started=time.monotonic();previous={}
    def request_stop(signum,frame):(out/'stop.request').write_text(str(signum))
    for sig in (signal.SIGINT,signal.SIGTERM):previous[sig]=signal.signal(sig,request_stop)
    with (out/'engine.log').open('xb') as elog,(out/'recorder.log').open('xb') as rlog:
        if spec['mode']!='render':
            rosen=os.environ.copy();rosen.update(ROS_DOMAIN_ID=str(spec['ros_domain_id']),ROS_LOCALHOST_ONLY='1',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
            regex=r'^/(lidar/[^/]+/points|camera/[^/]+/(image_raw|camera_info)|tf|clock|joint_states)$'
            bag=['ros2','bag','record','-s','mcap','-o',str(out/'bag'),'--regex',regex,
                 '--use-sim-time','--disable-keyboard-controls','--max-cache-size','268435456',
                 '--node-name','native_capture_baseline_recorder']
            if spec['mode']=='publish':bag.append('--start-paused')
            recorder=subprocess.Popen(ros_command(bag),env=rosen,stdin=subprocess.DEVNULL,stdout=rlog,stderr=rlog,start_new_session=True)
            result['recorder_pid']=recorder.pid
        soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE,(min(max(soft,65536),hard),hard))
        engine=subprocess.Popen(args,cwd=ISAAC,env=env,stdin=subprocess.DEVNULL,stdout=elog,stderr=elog,start_new_session=True)
        if not spec['trace']:(out/'kit.pid').write_text(str(engine.pid))
        result['supervised_pid']=engine.pid;write(out/'result.json',result)
        sampler=threading.Thread(target=sample,args=(out,stop,recorder),daemon=True);sampler.start()
        try:
            deadline=started+spec['timeout_s']
            while engine.poll() is None:
                if recorder and recorder.poll() is not None:raise RuntimeError('Recorder exited before engine')
                if time.monotonic()>deadline:raise TimeoutError('Native experiment deadline')
                time.sleep(.5)
            result['engine_exit']=engine.returncode
        except BaseException as exc:
            result['error']=type(exc).__name__+': '+str(exc);(out/'stop.request').write_text(str(exc))
            try:engine.wait(timeout=20)
            except subprocess.TimeoutExpired:close_child(engine,signal.SIGTERM,10)
            result['engine_exit']=engine.returncode
        finally:
            # Kit stopped publishing. Let DDS finish delivery, then SIGINT rosbag2 for proper metadata/footer.
            time.sleep(2);close_child(recorder,signal.SIGINT,30)
            result['recorder_exit']=recorder.returncode if recorder else None
            stop.set();sampler.join(timeout=8)
            for sig,handler in previous.items():signal.signal(sig,handler)
    result['process_wall_s']=time.monotonic()-started
    result['root_usd_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items())
    if (out/'engine_result.json').exists():result['capture']=json.loads((out/'engine_result.json').read_text())
    if spec['mode']=='record' and result['engine_exit']==0:
        check=subprocess.run(ros_command(['/usr/bin/python3',str(ROOT/'tools/validate_bag.py'),str(out)]),
                             capture_output=True,text=True,timeout=180)
        (out/'validation.log').write_text(check.stdout+check.stderr);result['validation_exit']=check.returncode
        if (out/'validation.json').exists():result['validation']=json.loads((out/'validation.json').read_text())
        if spec.get('experiment'):
            extra=subprocess.run(ros_command(['/usr/bin/python3',str(ROOT/'tools/validate_groups.py'),str(out)]),capture_output=True,text=True,timeout=240)
            (out/'group_validation.log').write_text(extra.stdout+extra.stderr)
            result['group_validation_exit']=extra.returncode
            if (out/'group_validation.json').exists():result['group_validation']=json.loads((out/'group_validation.json').read_text())
            if extra.returncode:result['validation_exit']=extra.returncode
    result['state']='completed' if result['engine_exit']==0 and result['root_usd_unchanged'] and not result.get('error') and (recorder is None or result['recorder_exit']==0) and (spec['mode']!='record' or result.get('validation_exit')==0) else 'failed'
    if spec['trace']:
        result['profile_capture_verified']=False
        if (out/'native.sqlite').is_file():
            with sqlite3.connect('file:'+str(out/'native.sqlite')+'?mode=ro',uri=True) as db:
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if {'NVTX_EVENTS','GPU_METRICS','StringIds'}<=tables:
                    windows=db.execute("SELECT count(*) FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id WHERE COALESCE(n.text,s.value)='NATIVE_CAPTURE_WINDOW' AND n.end>n.start").fetchone()[0]
                    result['profile_capture_verified']=windows>0 and db.execute('SELECT count(*) FROM GPU_METRICS').fetchone()[0]>0
        if not result['profile_capture_verified']:result['state']='failed';result['profile_error']='Requested Nsight profile evidence absent or empty'
    write(out/'result.json',result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default=str(ROOT/'config/baseline.json'))
    p.add_argument('--mode',choices=['render','publish','record']);p.add_argument('--frames',type=int)
    p.add_argument('--warmup',type=int);p.add_argument('--trace',action='store_true',default=None)
    p.add_argument('--multi-tick',action='store_true');p.add_argument('--schedule',choices=['continuous','frozen'])
    p.add_argument('--motion',choices=['static','moving']);p.add_argument('--trajectory');p.add_argument('--output')
    a=p.parse_args();spec=json.loads(Path(a.config).read_text())
    for attr,key in [('mode','mode'),('frames','measure_frames'),('warmup','warmup_frames'),('schedule','schedule'),('motion','motion'),('trajectory','trajectory')]:
        value=getattr(a,attr)
        if value is not None:spec[key]=value
    if a.trace is not None:spec['trace']=a.trace
    spec['multi_tick']=a.multi_tick or spec['multi_tick']
    out=a.output or str(Path(spec['output_root'])/(spec['mode']+'_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())))
    result=run(spec,out);print(json.dumps(result,indent=2));raise SystemExit(0 if result['state']=='completed' else 1)
if __name__=='__main__':main()
