from pathlib import Path
import json
root=Path('/root/isaacsim/extscache')
rows=[]
for pattern in ('omni.replicator.core-*','omni.hydratexture-*'):
    for folder in root.glob(pattern):
        for path in folder.rglob('*.py'):
            if 'test' in str(path): continue
            source=path.read_text(errors='replace'); lines=source.splitlines()
            hits=[i for i,line in enumerate(lines) if 'release_hydra' in line or ('def ' in line and 'hydra_texture' in line)]
            for i in hits[:6]: rows.append({'path':str(path),'line':i+1,'text':'\n'.join(lines[max(0,i-5):i+30])})
print(json.dumps(rows[:18]))
