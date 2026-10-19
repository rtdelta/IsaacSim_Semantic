from pathlib import Path
import json
root=Path('/root/isaacsim'); rows=[]
for base in list((root/'exts').glob('*sensors*rtx*')):
    for p in base.rglob('*'):
        if not p.is_file() or p.suffix not in ('.py','.ogn','.json','.md') or p.stat().st_size>200000: continue
        text=p.read_text(errors='replace')
        if any(term in text for term in ('IsaacExtractRTXSensorPointCloud','intensityPtr','GenericModelOutput')):
            lines=text.splitlines(); indices=[i for i,l in enumerate(lines) if any(term in l for term in ('IsaacExtractRTXSensorPointCloud','intensityPtr','GenericModelOutput'))]
            selected=sorted({j for i in indices for j in range(max(0,i-8),min(len(lines),i+30))})
            rows.append({'path':str(p),'text':'\n'.join(lines[i] for i in selected[:160])})
print(json.dumps(rows[:35]))
