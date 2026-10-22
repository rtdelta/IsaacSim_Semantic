import hashlib,json
from pathlib import Path
root=Path('/root/isaacsim/exts/isaacsim.core.simulation_manager');out=[]
for rel,start,end in [('isaacsim/core/simulation_manager/tests/test_simulation_manager.py',1030,1105),
    ('include/isaacsim/core/simulation_manager/TimeSampleStorage.h',35,100),
    ('isaacsim/core/simulation_manager/bindings/_simulation_manager.pyi',125,155)]:
    p=root/rel;lines=p.read_text().splitlines();out.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'start_line':start,'text':'\n'.join('%d: %s'%(i+1,lines[i]) for i in range(start-1,min(end,len(lines))))})
print(json.dumps(out))
