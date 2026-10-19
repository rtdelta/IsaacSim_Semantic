"""Static installed-source inspection; no Isaac/extension imports or writes."""
import json
from pathlib import Path
root=Path('/root/isaacsim/extscache');result=[]
for pattern in ('omni.replicator.core-*/omni/replicator/core/scripts/annotators.py',
                'omni.replicator.core-*/omni/replicator/core/scripts/utils/annotators_utils.py'):
 for p in root.glob(pattern):
  lines=p.read_text(errors='replace').splitlines();selected=[]
  for i,line in enumerate(lines):
   if 'do_array_copy' in line or 'def get_data(' in line:
    selected.append({'line':i+1,'excerpt':'\n'.join(lines[max(0,i-5):min(len(lines),i+18)])})
  result.append({'path':str(p),'excerpts':selected[:18]})
print(json.dumps(result,indent=2))
