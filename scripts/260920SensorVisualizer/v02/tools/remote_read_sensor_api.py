from pathlib import Path
import json
base=Path('/root/isaacsim')
results=[]
for folder in list((base/'extscache').glob('omni.replicator.core-*'))+[base/'exts/isaacsim.sensors.rtx.nodes']:
    for p in folder.rglob('*.py'):
        if p.stat().st_size>250000: continue
        text=p.read_text(errors='replace'); lines=text.splitlines()
        needles=['def get_annotator(', 'class OgnIsaacExtractRTXSensorPointCloud', 'def get_data(', 'def hydra_texture']
        for needle in needles:
            if needle not in text: continue
            indexes=[i for i,line in enumerate(lines) if needle in line]
            for i in indexes: results.append({'path':str(p),'source':'\n'.join(lines[max(0,i-4):i+110])})
for p in (base/'apps').glob('isaacsim.exp.*.kit'):
    if any(word in p.name for word in ('base','python','headless')):
        results.append({'path':str(p),'source':p.read_text()[:20000]})
print(json.dumps(results))
