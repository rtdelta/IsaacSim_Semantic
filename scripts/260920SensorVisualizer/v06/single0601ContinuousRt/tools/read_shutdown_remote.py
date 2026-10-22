"""Read only installed quit API declarations and task DISPLAY window metadata."""
import json
from pathlib import Path
import shutil
import subprocess
root=Path('/root/isaacsim')
hits=[]
for p in list((root/'kit/kernel/py').rglob('*.pyi'))+list((root/'kit/kernel/py').rglob('*.py')):
    data=p.read_text(errors='replace')
    if 'post_quit' in data:
        pos=data.find('post_quit')
        hits.append({'path':str(p),'snippet':data[max(0,pos-200):pos+1100]})
apps={name:shutil.which(name) for name in ('xdotool','xwininfo','wmctrl')}
windows=None
if apps['xwininfo']:
    windows=subprocess.run([apps['xwininfo'],'-display',':20','-root','-tree'],capture_output=True,text=True,timeout=5).stdout[-5000:]
print(json.dumps({'quit_declarations':hits[:12],'apps':apps,'window_metadata':windows}))
