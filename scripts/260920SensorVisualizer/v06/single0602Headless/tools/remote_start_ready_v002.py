"""Reload only this project's idle web service and start the delivered interactive GUI."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
sys.path.insert(0,str(root))
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.control_ipc import request
from single0602_headless.contracts import write_json
assert root.resolve()==root
regression=json.loads((root/'reports/continuous_capture_regression.json').read_text())
assert regression['state']=='passed'
supervisor=CaptureSupervisor(root,output,output/'runtime/engine.sock')
assert not supervisor.resource_busy() and not any(t['running'] or t.get('cleanup_pending') for t in supervisor.status())
try:
    current=request(output/'runtime/engine.sock',{'action':'status'},timeout=.5)
except (OSError,EOFError):current=None
assert current is None,'An engine is already connected; preserve it and inspect instead of replacing'
web=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        args=[a.decode() for a in (proc/'cmdline').read_bytes().split(b'\0') if a]
        if (proc/'cwd').resolve()==root and any(Path(a).name=='run_web.py' for a in args[1:]):
            web.append((int(proc.name),(proc/'cmdline').read_bytes()))
    except (OSError,UnicodeError):pass
assert len(web)<=1
stopped=[]
for pid,identity in web:
    proc=Path('/proc',str(pid))
    assert (proc/'cwd').resolve()==root and (proc/'cmdline').read_bytes()==identity
    os.kill(pid,signal.SIGTERM)
    deadline=time.monotonic()+5
    while proc.exists() and time.monotonic()<deadline:
        try:
            if proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[0]=='Z':break
        except OSError:break
        time.sleep(.1)
    stopped.append(pid)
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
env=os.environ.copy()
for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
with (root/'reports'/('web_v002_'+stamp+'.log')).open('wb') as log:
    web_process=subprocess.Popen(['/usr/bin/python3',str(root/'run_web.py')],cwd=root,env=env,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
env['DISPLAY']=':20'
if Path('/root/.Xauthority').is_file():env['XAUTHORITY']='/root/.Xauthority'
gui_log=root/'reports'/('interactive_v002_'+stamp+'.log')
with gui_log.open('wb') as log:
    gui_process=subprocess.Popen(['/usr/bin/python3',str(root/'run_capture.py'),'--interactive',
        '--job',str(root/'config/interactive.json')],cwd=root,env=env,stdin=subprocess.DEVNULL,
        stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
report={'state':'starting','version':'0.2.0','web_pid':web_process.pid,'gui_pid':gui_process.pid,
    'replaced_owned_web_pids':stopped,'gui_log':str(gui_log),'started_utc':stamp}
write_json(root/'reports/ready_v002.json',report)
print(json.dumps(report))
