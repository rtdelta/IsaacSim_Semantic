from pathlib import Path
import json
root=Path('/root/isaacsim/exts/isaacsim.sensors.experimental.rtx/isaacsim/sensors/experimental/rtx')
rows=[]
for p in (root/'generic_model_output').rglob('*.py'):
    text=p.read_text(errors='replace')
    if any(s in text for s in ('class GenericModelOutput','def getModelOutputFromBuffer','class BasicElements')):
        rows.append({'path':str(p),'text':text[:40000]})
for p in root.rglob('*generic*'):
    rows.append({'path':str(p),'text':p.read_text()[:15000] if p.is_file() and p.suffix=='.py' else 'directory'})
for directory in Path('/root/isaacsim/extscache').glob('omni.sensors.nv.common-*'):
    for p in directory.rglob('*.py'):
        if p.stat().st_size>200000: continue
        text=p.read_text(errors='replace')
        if any(s in text for s in ('class GenericModelOutput','def getModelOutputFromBuffer')):
            rows.append({'path':str(p),'text':text[:35000]})
for p in root.rglob('*.py'):
    if 'generic_model_output' in str(p):
        text=p.read_text()
        if any(s in text for s in ('class GenericModelOutput','def getModelOutputFromBuffer','class CoordsType')):
            lines=text.splitlines(); indices=[i for i,l in enumerate(lines) if any(s in l for s in ('class GenericModelOutput','def getModelOutputFromBuffer','class CoordsType'))]
            selected=sorted({j for i in indices for j in range(i,min(len(lines),i+125))})
            rows.append({'path':str(p),'text':'\n'.join(lines[i] for i in selected)})
print(json.dumps(rows))
