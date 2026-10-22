import json
from pathlib import Path
root=Path('/root/isaacsim')
out=[]
for pattern in ('exts/isaacsim.core.rendering_manager/**/*.py','exts/isaacsim.core.simulation_manager/**/simulation_manager.py'):
    for p in root.glob(pattern):
        lines=p.read_text(errors='replace').splitlines()
        if p.name=='rendering_manager.py':
            out.append({'path':str(p),'settings_constants':[line for line in lines if line.startswith('_SETTING')],
                        'set_dt_body':'\n'.join(lines[180:212])})
        for i,line in enumerate(lines):
            if any(s in line for s in ('def get_dt(','def set_dt(','def get_physics_dt(','def setup_simulation(')):
                out.append({'path':str(p),'line':i+1,'snippet':'\n'.join(lines[i:i+48])})
print(json.dumps(out))
