from pathlib import Path
import json
result=[]
for b in Path('/root/isaacsim').glob('exts*/omni.warp.core-*'):
 result.append({'root':str(b)})
 for p in b.rglob('builtins.py'):
  lines=p.read_text().splitlines();idx=set()
  for i,l in enumerate(lines):
   if '"mesh_query_point' in l or '"mesh_query_ray"' in l:
    idx.update(range(max(0,i-2),min(len(lines),i+43)))
  result.append({'path':str(p),'source':'\n'.join(lines[i] for i in sorted(idx))})
print(json.dumps(result))
