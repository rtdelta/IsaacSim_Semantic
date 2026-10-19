"""Encode only task source files for the audited SSH-stdin channel; no credentials."""
import base64,hashlib,json,zlib,sys
from pathlib import Path
R=Path(__file__).resolve().parent
records={}
selected=set(sys.argv[1:])
for p in R.rglob('*'):
    rel=p.relative_to(R)
    if selected and not any(rel.as_posix()==x or rel.as_posix().startswith(x+'/') for x in selected):continue
    if p.is_file() and not any(x in rel.parts for x in ('reports','results','deploy_history','operations','__pycache__')) and p.suffix in ('.py','.json','.md','.zip','.kit','.patch'):
        records[rel.as_posix()]={'data':base64.b64encode(p.read_bytes()).decode(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
payload=base64.b64encode(zlib.compress(json.dumps(records).encode())).decode()
script='''import base64,hashlib,json,zlib,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
root.mkdir(exist_ok=True)
records=json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))
changed=[]
for rel,row in records.items():
 p=root/rel
 if root.resolve() not in p.resolve().parents:raise RuntimeError('Outside task root')
 data=base64.b64decode(row['data']);assert hashlib.sha256(data).hexdigest()==row['sha256']
 if p.exists() and p.read_bytes()!=data:
  backup=root/'deploy_history'/time.strftime('%Y%m%d_%H%M%S',time.gmtime())/rel
  backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(p.read_bytes())
 if not p.exists() or p.read_bytes()!=data:
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);changed.append(rel)
(root/'reports').mkdir(exist_ok=True)
(root/'reports/deployment_manifest.json').write_text(json.dumps({r:v['sha256'] for r,v in records.items()},indent=2))
print(json.dumps({'verified_files':len(records),'changed_files':changed}))
'''.replace('PAYLOAD',repr(payload))
batches=[];batch={}
for rel,row in records.items():
    trial=dict(batch);trial[rel]=row
    if batch and len(base64.b64encode(zlib.compress(json.dumps(trial).encode())))>180000:
        batches.append(batch);batch={}
    batch[rel]=row
if batch:batches.append(batch)
for i,batch in enumerate(batches):
    encoded=base64.b64encode(zlib.compress(json.dumps(batch).encode())).decode()
    content=script.replace(repr(payload),repr(encoded))
    assert len(content.encode())<256*1024
    out=R/f'operations/deploy_{i}.py';out.write_text(content,encoding='utf-8')
print(json.dumps({'deploy_files':len(records),'batches':len(batches)}))
