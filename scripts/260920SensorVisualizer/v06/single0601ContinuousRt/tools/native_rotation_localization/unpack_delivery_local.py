"""Verify delivery and extract only regular members to a new project directory."""
import hashlib,json,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];archive=ROOT/'reports/remote/reports/native007_delivery_20261015.tar.gz';dest=ROOT/'reports/native007_delivery_20261015'
receipt=json.loads((ROOT/'reports/native007_pack_delivery_20261015.json').read_text())
if hashlib.sha256(archive.read_bytes()).hexdigest()!=receipt['archive_sha256']:raise RuntimeError('Archive hash mismatch')
dest.mkdir(exist_ok=False)
with tarfile.open(archive,'r:gz') as t:
 members=t.getmembers();names=set()
 for m in members:
  path=(dest/m.name).resolve()
  if not m.isfile() or dest.resolve() not in path.parents or m.name in names:raise RuntimeError('Unsafe archive member')
  names.add(m.name);path.parent.mkdir(parents=True,exist_ok=True)
  with t.extractfile(m) as src,path.open('xb') as out:shutil.copyfileobj(src,out)
manifest=json.loads((dest/'delivery_manifest.json').read_text())
for row in manifest['files']:
 p=dest/row['path']
 if p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('Delivery member mismatch '+row['path'])
if names!={r['path'] for r in manifest['files']}|{'delivery_manifest.json'}:raise RuntimeError('Unexpected archive members')
print(json.dumps({'destination':str(dest),'verified_files':len(manifest['files']),'archive_sha256':receipt['archive_sha256']}))
