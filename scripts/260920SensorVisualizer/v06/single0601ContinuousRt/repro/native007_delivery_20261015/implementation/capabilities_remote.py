import json,hashlib
from pathlib import Path
sdk=Path('/root/isaacsim');out={}
out['storage_roots']={str(p):[x.name for x in p.iterdir() if x.is_dir()] for p in (Path('/root/gpufree-data'),sdk)}
hits=[];contracts=[]
for base in (sdk/'apps',sdk/'exts',sdk/'extscache'):
 for p in base.rglob('*'):
  if not p.is_file():continue
  if p.suffix not in ('.py','.h','.kit','.toml','.rst') or p.stat().st_size>200000:continue
  t=p.read_text(errors='replace')
  keys=['persistent/isaac/asset_root','asset_root.default','convert_json','json_to_usd','getHistoryTransform','get_transform_history','interpolationWeight','queryTimestamp','modelToAppTransform']
  if any(k in t for k in keys):
   lines=t.splitlines();rows=[{'line':i+1,'lines':lines[max(0,i-2):i+4]} for i,l in enumerate(lines) if any(k in l for k in keys)]
   hits.append({'path':str(p),'hits':rows[:12]})
  if p.name=='GenericModelOutputTypes.h':contracts.append({'path':str(p),'lines':t.splitlines()})
out.update(hits=hits,contracts=contracts)
print(json.dumps(out))
