"""Encode self-generated figures in bounded audited transfer chunks."""
from pathlib import Path
import base64,hashlib,json
R=Path(__file__).resolve().parent;counter=0;manifest={}
for p in sorted((R/'docs/figures').glob('*.png')):
 data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();rel=p.relative_to(R).as_posix();manifest[rel]=sha
 for offset in range(0,len(data),120000):
  chunk=data[offset:offset+120000];last=offset+len(chunk)==len(data)
  code="""import base64,hashlib,json,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
p=root/REL
assert p.resolve().is_relative_to(root/'docs/figures')
p.parent.mkdir(parents=True,exist_ok=True)
part=p.with_name(p.name+'.'+SHA[:12]+'.part')
data=base64.b64decode(DATA)
if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==SHA:print(json.dumps({'verified':REL,'existing':True}))
else:
 if OFFSET==0:
  with part.open('xb') as f:f.write(data)
 else:
  assert part.stat().st_size==OFFSET
  with part.open('ab') as f:f.write(data)
 if LAST:
  assert hashlib.sha256(part.read_bytes()).hexdigest()==SHA
  if p.exists():
   backup=root/'deploy_history'/time.strftime('%Y%m%d_%H%M%S',time.gmtime())/REL
   backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(p.read_bytes())
  part.replace(p)
 print(json.dumps({'path':REL,'offset':OFFSET,'bytes':len(data),'complete':LAST}))
""".replace('REL',repr(rel)).replace('SHA',repr(sha)).replace('DATA',repr(base64.b64encode(chunk).decode())).replace('OFFSET',str(offset)).replace('LAST',str(last))
  (R/f'operations/deploy_media_{counter}.py').write_text(code,encoding='utf-8');counter+=1
(R/'media_manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'chunks':counter,'figures':len(manifest)}))
