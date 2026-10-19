from pathlib import Path
import json
out={'x_sockets':[p.name for p in Path('/tmp/.X11-unix').glob('X*')],'processes':[]}
for p in Path('/proc').glob('[0-9]*'):
    try:
        name=(p/'comm').read_text().strip()
        if name.lower() in ('xorg','selkies','xfce4-session'):
            env=dict(item.split('=',1) for item in (p/'environ').read_bytes().decode(errors='replace').split(chr(0)) if '=' in item)
            row={'pid':p.name,'name':name,'env':{k:env.get(k) for k in ('DISPLAY','XAUTHORITY')}}
            if name.lower()=='xorg': row['command']=(p/'cmdline').read_bytes().replace(bytes([0]),b' ').decode(errors='replace')
            out['processes'].append(row)
    except (OSError,ValueError): pass
print(json.dumps(out))
