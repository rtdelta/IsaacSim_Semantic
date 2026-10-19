from pathlib import Path
import json
paths=list(Path('/root/isaacsim/extscache').glob('omni.replicator.core-*/omni/replicator/core/scripts/utils/annotator_utils.py'))
results=[]
for p in paths:
    lines=p.read_text().splitlines(); results.append({'path':str(p),'source':'\n'.join(f'{i+1}: {lines[i]}' for i in range(410,590))})
print(json.dumps(results))
