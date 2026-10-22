from pathlib import Path
import json
rows=[]
for b in Path('/root/isaacsim/extscache').glob('omni.replicator.core-*'):
 for p in b.rglob('annotator_utils.py'):
  lines=p.read_text().splitlines();ranges=[]
  for i,l in enumerate(lines):
   if any(t in l for t in ('def get_annotator_data(', 'annotator_id]', 'def _get_annotator_data(', 'def _get_data')):ranges.append((max(0,i-8),min(len(lines),i+100)))
  indices=list(range(340,509))
  rows.append({'path':str(p),'source':'\n'.join(f'{i+1}: {lines[i]}' for i in indices)})
print(json.dumps(rows))
