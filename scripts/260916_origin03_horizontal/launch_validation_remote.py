import json, os, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer')
out=root/'validation/results/origin03_horizontal'
result=out/'kit_validation.json'
if result.exists():
    result.rename(out/('kit_validation_previous_'+str(result.stat().st_mtime_ns)+'.json'))
env=os.environ.copy();env['ROS_DOMAIN_ID']='151'
(out/'progress.json').write_text(json.dumps({'phase':'starting'}))
with (out/'kit_validation.log').open('w') as log:
    process=subprocess.Popen(['python3',str(root/'launch_isaac.py'),'--no-window',
        '--/app/window/enabled=false','--/app/viewport/defaults/visible=true',
        '--/log/file='+str(out/'kit_detail.log'),
        '--exec',str(root/'validation/validate_horizontal_isaac.py')],
        cwd=str(root),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(out/'validation_pid.json').write_text(json.dumps({'pid':process.pid}))
watchdog = '''import os,signal,sys,time
from pathlib import Path
pid=int(sys.argv[1]);result=Path(sys.argv[2]);start=time.monotonic()
while not result.exists() and time.monotonic()-start<180:
    if not Path('/proc/'+str(pid)).exists():sys.exit(0)
    time.sleep(1)
time.sleep(5)
for sig in (signal.SIGTERM,signal.SIGKILL):
    path=Path('/proc/'+str(pid)+'/cmdline')
    if path.exists() and b'validation/validate_horizontal_isaac.py' in path.read_bytes() and os.getpgid(pid)==pid:
        os.killpg(pid,sig)
    time.sleep(5)
'''
with (out/'watchdog.log').open('w') as log:
    subprocess.Popen(['python3','-c',watchdog,str(process.pid),str(result)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'pid':process.pid,'log':str(out/'kit_validation.log')}))
