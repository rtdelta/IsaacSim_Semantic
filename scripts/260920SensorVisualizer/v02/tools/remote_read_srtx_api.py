from pathlib import Path
import json
base=Path('/root/isaacsim'); results=[]
directories=list((base/'extscache').glob('omni.replicator.srtx-*'))+list((base/'exts').glob('*srtx*'))
for directory in directories:
    for p in directory.rglob('*.py'):
        text=p.read_text(errors='replace')
        if any(n in text for n in ('def get_annotator','class','hydra_texture','def get_data')):
            results.append({'path':str(p),'source':text[:50000]})
for p in (base/'extscache').glob('omni.services.transport.server.http-*/config/extension.toml'):
    results.append({'path':str(p),'source':p.read_text()})
print(json.dumps(results))
