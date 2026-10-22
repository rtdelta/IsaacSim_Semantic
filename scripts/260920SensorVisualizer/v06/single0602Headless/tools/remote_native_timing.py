"""Read installed timing settings and physics dt implementation without imports."""
import json
from pathlib import Path
roots=[]
for parent in ('/root/isaacsim/exts','/root/isaacsim/kit/exts','/root/isaacsim/kit/extscore','/root/isaacsim/extscache'):
    for pattern in ('*loop*','*simulation_app*'):
        roots.extend(Path(parent).glob(pattern))
print(json.dumps({'roots':[str(p) for p in roots]}))
terms=('manual_mode','manual_step','loop_runner','manualModeEnabled','acquire_loop')
for root in roots:
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix not in ('.kit','.py','.pyi','.toml'):continue
        lines=path.read_text(errors='replace').splitlines();selected=set()
        for i,line in enumerate(lines):
            if any(term in line for term in terms):selected.update(range(max(0,i-3),min(len(lines),i+12)))
        if selected:print(json.dumps({'path':str(path),'lines':['%d: %s'%(i+1,lines[i]) for i in sorted(selected)]}))
