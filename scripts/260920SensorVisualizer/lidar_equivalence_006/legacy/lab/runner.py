"""Owned child supervisor for ordinary runs and short native capture windows."""
import argparse,copy,hashlib,json,os,signal,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from .resources import Sampler

ROOT=Path(__file__).resolve().parents[1]
NSYS='/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys'

def write(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)

def prepare(spec,directory):
    sys.path.insert(0,str(ROOT/'frozen_runtime'))
    from sensor_visualizer_v06.trajectory import Trajectory
    from sensor_visualizer_v06.contracts import load_job
    from run_capture import launch_spec
    source=Path(spec['trajectory']);trajectory=Trajectory.load(source)
    dest=directory/'input_trajectory';dest.mkdir()
    metadata=copy.deepcopy(trajectory.metadata);states=copy.deepcopy(trajectory.states)
    if spec.get('pose')=='static':
        first=states[0]
        for row in states:
            for key in ('position_world_m','quaternion_xyzw','joints_deg','mounts','mount_revision'):
                row[key]=copy.deepcopy(first[key])
        metadata['mount_revisions']={str(first['mount_revision']):first['mounts']}
    write(dest/'metadata.json',metadata)
    (dest/'states.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in states),encoding='utf-8')
    job=load_job(ROOT/'frozen_runtime/config/offline.json')
    job.update(groups=spec.get('groups',8),scene=spec['scene'],output_directory=str(directory/'captures'))
    job['render']['background_dome']=None
    job['render']['warmup_subframes']=16;job['render']['camera_subframes']=16;job['render']['capture_subframes']=2
    job['capture']['resource_policy']=spec.get('policy','gated')
    job['diagnostics'].update(level='deep',native_profiler='nvtx' if spec.get('trace_window','none')!='none' else 'off',
                               event_queue_capacity=32768,detail_group_range=None)
    job['replay']={'mode':'offline','trajectory':str(dest),'control_path':str(directory/'control.json'),
                   'status_path':str(directory/'capture_status.json'),
                   'socket':str(directory/'engine.sock')}
    write(directory/'job.json',job);write(directory/'spec.json',spec)
    args,env,install=launch_spec(directory/'job.json',entry=ROOT/'kit_lab_entry.py')
    env['SL06_SPEC']=str(directory/'spec.json');env['SL06_PID_FILE']=str(directory/'kit.pid')
    return job,args,env,install

def run(spec,output,allow_coexisting=False):
    if os.name!='posix':raise RuntimeError('Run on the Linux Isaac instance')
    if not allow_coexisting:
        for p in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                if b'/kit/kit' in p.read_bytes().split(b'\0')[0]:
                    raise RuntimeError('An existing Isaac process is running; isolated experiment did not stop it')
            except (OSError,IndexError):pass
    directory=Path(output).resolve();directory.mkdir(parents=True,exist_ok=False)
    try:job,args,env,install=prepare(spec,directory)
    except Exception as exc:
        write(directory/'result.json',{'spec':spec,'directory':str(directory),'exit_code':1,
              'state':'prepare_failed','error':type(exc).__name__+': '+str(exc)})
        raise
    trace=spec.get('trace_window','none')!='none'
    if trace:
        # NVTX A-string markers are intentionally unregistered. Nsight's
        # registered-only default otherwise silently misses the capture trigger.
        env['NSYS_NVTX_PROFILER_REGISTER_ONLY']='0'
        args=[NSYS,'profile','--trace=vulkan,cuda,nvtx,osrt','--sample=process-tree',
            '--cpuctxsw=process-tree','--backtrace=lbr','--vulkan-gpu-workload=batch',
            '--capture-range=nvtx','--nvtx-capture=SL06_WINDOW','--capture-range-end=stop',
            '--gpu-metrics-devices=0','--gpu-metrics-set='+spec.get('metrics_set','ad10x'),
            '--gpu-metrics-frequency='+str(spec.get('metrics_hz',1000)),
            '--export=sqlite','--output='+str(directory/'native'),*args]
        if spec.get('native_memory_stacks',False):
            args[2:2]=['--cuda-memory-usage=true','--cudabacktrace=memory:1000000,sync:1000000']
    result={'spec':spec,'directory':str(directory),'started_utc':datetime.now(timezone.utc).isoformat(),
            'profiled':trace,'exit_code':None,'validation':None,
            'quality':job['render'],'hardware_metrics_scope':'entire GPU, not per process'}
    write(directory/'result.json',result)
    with (directory/'engine.log').open('xb') as log:
        process=subprocess.Popen(args,env=env,cwd=str(install),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        if not trace:(directory/'kit.pid').write_text(str(process.pid))
        result['supervised_pid']=process.pid;write(directory/'result.json',result)
        sampler=Sampler(directory,directory/'kit.pid');sampler.start();started=time.monotonic()
        previous_handlers={}
        def stop_request(signum,frame):
            result['external_stop_signal']=signum
            write(directory/'control.json',{'action':'stop'})
        for sig in (signal.SIGTERM,signal.SIGINT):
            previous_handlers[sig]=signal.signal(sig,stop_request)
        try:
            deadline=started+spec.get('timeout_s',600)
            while process.poll() is None:
                status_path=directory/'capture_status.json'
                if spec.get('stop_after_groups') and not result.get('controlled_stop_requested') and status_path.is_file():
                    status=json.loads(status_path.read_text())
                    if status.get('groups',0)>=spec['stop_after_groups']:
                        write(directory/'control.json',{'action':'stop'});result['controlled_stop_requested']=True
                if time.monotonic()>deadline:
                    write(directory/'control.json',{'action':'stop'});result['timeout_requested']=True
                    try:process.wait(timeout=45)
                    except subprocess.TimeoutExpired:
                        # Only this task's process group created by start_new_session.
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=15)
                        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    break
                time.sleep(.2)
        finally:
            sampler.close()
            for sig,handler in previous_handlers.items():signal.signal(sig,handler)
    result.update(exit_code=process.returncode,process_wall_s=time.monotonic()-started)
    status=directory/'capture_status.json'
    if status.is_file():result['capture']=json.loads(status.read_text())
    if process.returncode==0 and result.get('capture',{}).get('state')=='finished':
        sessions=json.loads((directory/'sessions.json').read_text()) if (directory/'sessions.json').is_file() else [result['capture']['session']]
        result['episode_validations']=[]
        for index,session in enumerate(sessions):
            v=subprocess.run(['/bin/bash','--noprofile','--norc','-c',
                'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','sl06-validation',
                str(ROOT/'tools/validate_capture_data.py'),session],capture_output=True,text=True,timeout=180)
            (directory/('validation_'+str(index)+'.log')).write_text(v.stdout+'\n'+v.stderr)
            result['validation_exit_code']=v.returncode
            for line in v.stdout.splitlines():
                if line.startswith('VALIDATION_JSON='):
                    result['validation']=json.loads(line[len('VALIDATION_JSON='):]);result['episode_validations'].append(result['validation'])
        if len(result['episode_validations'])!=len(sessions):result['validation']={'passed':False,'reason':'Not every episode validated'}
    result['completed_utc']=datetime.now(timezone.utc).isoformat();write(directory/'result.json',result)
    if trace:
        result['native_files']={p.name:p.stat().st_size for p in directory.glob('native*') if p.is_file()}
        result['profile_capture_verified']=False
        if (directory/'native.sqlite').is_file():
            import sqlite3
            with sqlite3.connect(str(directory/'native.sqlite')) as db:
                tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if {'NVTX_EVENTS','GPU_METRICS','StringIds'}<=tables:
                    windows=db.execute("SELECT count(*) FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id WHERE COALESCE(n.text,s.value)='SL06_WINDOW' AND n.end>n.start").fetchone()[0]
                    result['profile_capture_verified']=windows>0 and db.execute('SELECT count(*) FROM GPU_METRICS').fetchone()[0]>0
        write(directory/'result.json',result)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',required=True);p.add_argument('--output',required=True)
    p.add_argument('--allow-coexisting',action='store_true');a=p.parse_args()
    r=run(json.loads(Path(a.spec).read_text()),a.output,a.allow_coexisting)
    print(json.dumps({'directory':r['directory'],'exit_code':r['exit_code'],'validation':r['validation']},indent=2))
    return 0 if r['exit_code']==0 and r.get('validation',{}).get('passed') and r.get('profile_capture_verified',True) else 1
if __name__=='__main__':raise SystemExit(main())
