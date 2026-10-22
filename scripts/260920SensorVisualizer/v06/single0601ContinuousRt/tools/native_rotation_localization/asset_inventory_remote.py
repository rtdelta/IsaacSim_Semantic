import os,json
from pathlib import Path
matches=[]
for root in ('/root/isaacsim','/root/gpufree-data'):
 for parent,dirs,files in os.walk(root):
  dirs[:]=[d for d in dirs if d not in ('reports','.git','.deploy_backups','node_modules','__pycache__','site-packages','pip_prebundle','pip_core_prebundle','lost+found')]
  for name in files:
   if 'example' in name.lower() and name.lower().endswith(('.usd','.usda','.usdc')):
    p=Path(parent)/name;matches.append({'path':str(p),'bytes':p.stat().st_size})
print(json.dumps({'official_example_usd_candidates':matches}))
