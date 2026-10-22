from pathlib import Path
import json
rows=[]
for p in Path('/root/isaacsim/extscache').glob('omni.replicator.core-*/omni/replicator/core/scripts/writers.py'):
    lines=p.read_text().splitlines(); marks=[i for i,l in enumerate(lines) if 'Writer version not specified' in l or 'def get_metadata' in l or 'def __init__' in l][:15]
    positions=sorted({j for i in marks for j in range(max(0,i-12),min(len(lines),i+24))})
    rows.append({'path':str(p),'text':'\n'.join(lines[i] for i in positions)})
print(json.dumps(rows))
