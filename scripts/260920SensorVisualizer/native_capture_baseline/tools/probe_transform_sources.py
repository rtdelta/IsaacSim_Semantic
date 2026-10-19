import json,subprocess
from pathlib import Path
roots=[Path('/root/isaacsim/exts'),Path('/root/isaacsim/extscache')]
names=['*ComputeTransformTree*','*ReadJointState*']
files=[]
for root in roots:
 for name in names:
  for p in root.glob('isaacsim.*/**/'+name):
   if p.is_file() and p.suffix in ('.py','.ogn','.json') and '__pycache__' not in str(p):
    files.append({'path':str(p),'text':p.read_text(errors='replace')[:15000]})
print(json.dumps({'files':files}))
