"""Read installed declarations only; no import, SDK download or native invocation."""
import hashlib,json,re
from pathlib import Path
root=Path('/root/isaacsim');matches=[];files=[]
for parent in (root/'exts',root/'extscache'):
    if not parent.exists():continue
    for extension in parent.iterdir():
        if not any(x in extension.name for x in ('simulation_manager','omni.sensors','usdrt','fabric')):continue
        for p in extension.rglob('*'):
            if not p.is_file() or p.suffix not in ('.py','.pyi','.h','.md','.ogn','.rst') or p.stat().st_size>4*1024**2:continue
            text=p.read_text(errors='replace');lines=text.splitlines();found=[]
            for i,line in enumerate(lines):
                if re.search(r'ExternalSimulationTime|TimeSampleStorage|get_simulation_time_at_time|history.*transform|transform.*history|omni:time',line,re.I):
                    found.append({'line':i+1,'text':'\n'.join(lines[max(0,i-2):min(len(lines),i+5)])})
            if found:matches.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'matches':found[:20]})
print(json.dumps({'scope':'installed read-only declarations; CPU queries do not prove GPU ray history','matches':matches[:60]}))
