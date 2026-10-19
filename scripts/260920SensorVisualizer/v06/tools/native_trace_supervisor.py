"""Bounded lifetime for task-owned Nsight process group; no global process matching."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
out=Path(sys.argv[1]);spec=json.loads((out/'launch.json').read_text())
sys.path.insert(0,spec['project'])
from run_capture import launch_spec
_,env,_=launch_spec(out/'job.json',entry=Path(spec['project'])/'tools/native_capture_entry.py')
env['NSYS_NVTX_PROFILER_REGISTER_ONLY']='0'
with (out/'nsys.log').open('ab') as log:
    p=subprocess.Popen(spec['command'],cwd=spec['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    ticks=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    (out/'process.json').write_text(json.dumps({'pid':p.pid,'start_ticks':ticks}))
    started=time.monotonic();timeout=False
    try:code=p.wait(timeout=600)
    except subprocess.TimeoutExpired:
        timeout=True;os.killpg(p.pid,signal.SIGTERM)
        try:code=p.wait(timeout=20)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);code=p.wait(timeout=10)
    (out/'result.json').write_text(json.dumps({'exit_code':code,'timeout':timeout,'wall_s':time.monotonic()-started}))
sys.exit(code)
