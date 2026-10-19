import json
from pathlib import Path
root=Path('/root/isaacsim/exts/isaacsim.core.throttling')
for path in root.rglob('*.py'):
    if 'tests' in path.parts:continue
    lines=path.read_text().splitlines();selected=set()
    for i,line in enumerate(lines):
        if any(term in line for term in ('manual_mode','manual_step','enable_async','useFixedTimeStepping','_on_update','def on_startup')):
            selected.update(range(max(0,i-6),min(len(lines),i+26)))
    if selected:print(json.dumps({'path':str(path),'lines':['%d: %s'%(i+1,lines[i]) for i in sorted(selected)]}))
