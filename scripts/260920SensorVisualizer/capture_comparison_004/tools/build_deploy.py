import base64,hashlib,io,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];manifest={}
with io.BytesIO() as buf:
 with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted(root.rglob('*')):
   if not p.is_file() or any(x in p.relative_to(root).parts for x in ('reports','__pycache__','backups','deploy_history','results')):continue
   rel=p.relative_to(root).as_posix();b=p.read_bytes();z.writestr(rel,b);manifest[rel]=hashlib.sha256(b).hexdigest()
 payload=base64.b64encode(buf.getvalue()).decode()
code='''import base64,hashlib,io,json,time,zipfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004')
if root.parent.resolve()!=root.parent or root.exists() and root.resolve()!=root:raise RuntimeError('Unexpected symlink')
root.mkdir(exist_ok=True);(root/'reports').mkdir(exist_ok=True)
old={};excluded={'reports','__pycache__','backups','deploy_history','vendor','.venv-web','.git'}
for name in ('v06','single06_lab','native_capture_baseline','native_capture_quality_002','native_capture_continuous_pt_003'):
 for p in sorted((root.parent/name).rglob('*')):
  if p.is_file() and not any(x in excluded for x in p.relative_to(root.parent/name).parts):old[p.relative_to(root.parent).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
record=root/'reports/preserved_remote.json'
if not record.exists():
 record.write_text(json.dumps(old,indent=2));(root/'backups').mkdir(exist_ok=True)
 with zipfile.ZipFile(root/'backups/pre_NC004_sources.zip','x',zipfile.ZIP_DEFLATED) as z:
  for rel in old:z.write(root.parent/rel,rel)
elif json.loads(record.read_text())!=old:raise RuntimeError('Preserved source changed')
expected=MANIFEST;changes=[];stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime())
with zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD))) as z:
 for rel in z.namelist():
  p=root/rel;b=z.read(rel)
  if not p.resolve().is_relative_to(root) or hashlib.sha256(b).hexdigest()!=expected[rel]:raise RuntimeError('Invalid payload')
  if p.exists() and p.read_bytes()==b:continue
  if p.exists():
   backup=root/'deploy_history'/stamp/rel;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(p.read_bytes())
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);changes.append(rel)
assert all(hashlib.sha256((root/rel).read_bytes()).hexdigest()==h for rel,h in expected.items())
(root/'reports/deployment.json').write_text(json.dumps({'hashes':expected,'changed':changes},indent=2))
print(json.dumps({'verified':len(expected),'preserved':len(old),'changed':changes}))
'''.replace('MANIFEST',repr(manifest)).replace('PAYLOAD',repr(payload))
if len(code.encode())>256*1024:raise RuntimeError('Deployment exceeds audit cap')
(root/'reports/deploy_reviewed.py').write_text(code,encoding='utf-8');print(json.dumps({'files':len(manifest),'script_bytes':len(code.encode())}))
