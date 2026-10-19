"""Start one isolated task-owned capture; no broad process termination."""
import datetime, json, os, subprocess, sys
from pathlib import Path
ROOT=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try: args=p.read_bytes().split(b'\0')
    except OSError: continue
    if args[0].endswith(b'/kit/kit'):raise RuntimeError('A live Isaac process exists; refusing concurrent renderer')
groups=int(sys.argv[1]) if len(sys.argv)>1 else 3
output=Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer')/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+f'_{groups:03d}')
env=os.environ.copy()
for key in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
prep=subprocess.run(['/usr/bin/python3',str(ROOT/'prepare_capture.py'),str(output),'--groups',str(groups)],env=env,capture_output=True,text=True,timeout=30)
if prep.returncode:raise RuntimeError(prep.stderr)
log=(output/'supervisor.log').open('xb')
child=subprocess.Popen(['/usr/bin/python3','-u','-m','lab.runner','--spec',str(output/'input_spec.json'),'--output',str(output/'capture')],cwd=ROOT/'capture_runtime',env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
record={'groups':groups,'directory':str(output),'pid':child.pid,'launched_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(ROOT/'reports').mkdir(exist_ok=True)
(ROOT/'reports/latest_capture.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record))
