"""Bounded, identity-checked owner of this experiment's process group."""
import json, os, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads(Path(sys.argv[1]).read_text());OUT=Path(SPEC['out'])
NSYS='/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys'
def identity(pid):
    try:
        row=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'start':row[19],'parent':int(row[1]),'state':row[0]}
    except (OSError,ValueError,IndexError):return None
env=os.environ.copy();env.update(SV04_EXPERIMENT_SPEC=str(Path(sys.argv[1]).resolve()),PYTHONDONTWRITEBYTECODE='1')
env['SV04_TEST_OUT']=str(OUT)
cmd=['/usr/bin/python3',str(ROOT/'run_capture.py'),'--job',SPEC['job'],
     '--entry',str(ROOT/SPEC.get('entry','experiments/probe_in_kit.py'))]
cmd+=SPEC.get('kit_settings',[])
cwd=ROOT
if SPEC.get('direct_kit'):
    sys.path.insert(0,str(ROOT))
    from run_capture import launch_spec
    os.environ.update(env)
    cmd,env,cwd=launch_spec(SPEC['job'],entry=str(ROOT/SPEC.get('entry','experiments/probe_in_kit.py')),
                            extra=SPEC.get('kit_settings',[]))
if SPEC.get('native'):
    env['NSYS_NVTX_PROFILER_REGISTER_ONLY']='0'
    cmd=[NSYS,'profile','--trace=vulkan,cuda,nvtx,osrt','--sample=process-tree','--cpuctxsw=process-tree',
         '--backtrace=lbr','--capture-range=nvtx','--nvtx-capture=SV04_PROFILE',
         '--capture-range-end=stop','--export=sqlite','--output='+str(OUT/'native')]+cmd
    if SPEC.get('batch_vulkan'):
        cmd.insert(2,'--vulkan-gpu-workload=batch')
with (OUT/'kit.log').open('wb') as log:
    child=subprocess.Popen(cmd,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    owned=identity(child.pid);start=time.monotonic();descendants={};result={}
    (OUT/'process.json').write_text(json.dumps({'pid':child.pid,'identity':owned,'command':cmd},indent=2))
    while child.poll() is None:
        for p in Path('/proc').glob('[0-9]*'):
            row=identity(p.name)
            if row and (row['parent']==child.pid or row['parent'] in descendants):descendants[int(p.name)]=row['start']
        if time.monotonic()-start>SPEC.get('timeout_s',600):
            if identity(child.pid)==owned:
                result['timeout']=True;os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
            break
        time.sleep(1)
    result.update(exit_code=child.returncode,wall_s=time.monotonic()-start)
    leftovers=[]
    for pid,tick in descendants.items():
        row=identity(pid)
        if row and row['start']==tick and row['state']!='Z':os.kill(pid,signal.SIGTERM);leftovers.append(pid)
    result['leftover_owned_children_terminated']=leftovers
(OUT/'supervisor_result.json').write_text(json.dumps(result,indent=2))
