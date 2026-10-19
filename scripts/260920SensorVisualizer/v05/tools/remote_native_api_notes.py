import json
from pathlib import Path
root=Path('/root/isaacsim');out={}
for base in list((root/'extscache').glob('omni.appwindow-*'))+list((root/'kit/exts').glob('omni.appwindow*')):
    for p in base.rglob('*.pyi'):
        text=p.read_text(errors='replace');lines=text.splitlines()
        for i,line in enumerate(lines):
            if any(name in line for name in ('def is_focused','def get_input_blocking_state','def get_keyboard','def subscribe_to_keyboard')):
                out[str(p)]=out.get(str(p),[])+lines[i:i+10]
print(json.dumps({'appwindow_interfaces':out,'display_sockets':[str(p) for p in Path('/tmp/.X11-unix').glob('X*')]}))
