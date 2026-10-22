import datetime, json, os, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
env=os.environ.copy();env.update(DISPLAY=':20',QT_X11_NO_MITSHM='1')
for key in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
log_path=root/'reports'/('gui_stdout_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.log')
log=log_path.open('xb')
child=subprocess.Popen(['/bin/bash','--noprofile','--norc',str(root/'launch_viewer.sh')],env=env,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/'reports/gui_process.json').write_text(json.dumps({'pid':child.pid,'log':str(log_path)}))
print(json.dumps({'pid':child.pid,'log':str(log_path)}))
