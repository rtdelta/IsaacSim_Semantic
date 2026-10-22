import json,os,signal,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
stopped=[]
for filename,keys in [('gui_process.json',['pid']),('isolated_gui_process.json',['viewer_pid','xvfb_pid'])]:
    p=root/'reports'/filename
    if not p.exists():continue
    value=json.loads(p.read_text())
    for key in keys:
        pid=int(value[key]);proc=Path('/proc')/str(pid)/'cmdline'
        if not proc.exists():continue
        args=proc.read_bytes().split(b'\0')
        if key=='xvfb_pid':assert args[:2]==[b'/usr/bin/Xvfb',b':88'],args
        else:assert (str(root/'run_viewer.py').encode() in args or (b'run_viewer.py' in args and (Path('/proc')/str(pid)/'cwd').resolve()==root)),args
        os.kill(pid,signal.SIGINT if key!='xvfb_pid' else signal.SIGTERM)
        for _ in range(30):
            if not proc.exists() or not proc.read_bytes():break
            time.sleep(.1)
        stopped.append({'pid':pid,'key':key,'exited':not proc.exists() or not proc.read_bytes()})
print(json.dumps({'stopped_owned_tests':stopped}))
