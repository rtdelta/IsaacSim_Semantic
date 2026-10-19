import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
assert not Path('/tmp/.X88-lock').exists(),'Display already owned; do not overwrite it'
env=os.environ.copy();env['DISPLAY']=':88';env['LIBGL_ALWAYS_SOFTWARE']='1'
log=(root/'reports/isolated_gui.log').open('wb')
# Existing Xvfb creates a test-only display, without changing the desktop.
x=subprocess.Popen(['/usr/bin/Xvfb',':88','-screen','0','1280x800x24','-nolisten','tcp'],stdout=log,stderr=log,start_new_session=True)
p=subprocess.Popen(['/bin/bash','--noprofile','--norc',str(root/'launch_viewer.sh'),'--port','8770','--domain-id','56'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/'reports/isolated_gui_process.json').write_text(json.dumps({'xvfb_pid':x.pid,'viewer_pid':p.pid}))
print(json.dumps({'xvfb_pid':x.pid,'viewer_pid':p.pid}))
