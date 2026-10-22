"""Build an audited, project-only deployment script. No dependency downloads."""
import argparse,base64,hashlib,io,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files={}
p=argparse.ArgumentParser();p.add_argument('--kind',choices=('all','code','docs'),default='all');a=p.parse_args()
with io.BytesIO() as buffer:
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(ROOT.rglob('*')):
            if not p.is_file() or any(x in p.relative_to(ROOT).parts for x in ('__pycache__','reports','generated','deploy_history')):continue
            rel=p.relative_to(ROOT).as_posix()
            is_doc=rel.startswith('docs/')
            if a.kind=='docs' and not is_doc:continue
            if a.kind=='code' and is_doc:continue
            z.writestr(rel,p.read_bytes());files[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
    payload=base64.b64encode(buffer.getvalue()).decode()
code='''# Project deployment from reviewed local source; backups before any overwrite.
import base64,hashlib,io,json,os,time,zipfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
if root.resolve()!=root:raise RuntimeError('Unexpected project root symlink')
target=root/'single06_lab'
if target.exists() and target.resolve()!=target:raise RuntimeError('Lab path symlink')
stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime())
backup=root/'backups'/('single06_before_lab_'+stamp+'.zip')
backup.parent.mkdir(exist_ok=True)
baseline=root/'v06'
with zipfile.ZipFile(backup,'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(baseline.rglob('*')):
  if p.is_file() and not any(x in p.relative_to(baseline).parts for x in ('__pycache__','reports','deploy_history','.venv-web')):
   z.write(p,p.relative_to(baseline).as_posix())
payload=base64.b64decode(PAYLOAD)
expected=MANIFEST
target.mkdir(exist_ok=True)
changes=[]
with zipfile.ZipFile(io.BytesIO(payload)) as z:
 for rel in z.namelist():
  p=target/rel
  if p.resolve().is_relative_to(target) is False:raise RuntimeError('Unsafe archive member')
  data=z.read(rel)
  if hashlib.sha256(data).hexdigest()!=expected[rel]:raise RuntimeError('Payload mismatch')
  if p.is_file() and p.read_bytes()==data:continue
  if p.exists():
   saved=target/'deploy_history'/stamp/rel;saved.parent.mkdir(parents=True,exist_ok=True)
   saved.write_bytes(p.read_bytes())
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);changes.append(rel)
observed={r:hashlib.sha256((target/r).read_bytes()).hexdigest() for r in expected}
assert observed==expected
source_checks={}
for rel,digest in expected.items():
 if rel.startswith('frozen_runtime/'):
  original=baseline/rel[len('frozen_runtime/'):]
  source_checks[rel]=original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()==digest
assert all(source_checks.values()),'Frozen copy differs from formal baseline'
(target/'reports').mkdir(exist_ok=True)
(target/'reports/deployment.json').write_text(json.dumps({'backup':str(backup),'hashes':observed,
 'formal_matches_frozen':source_checks,'changed':changes},indent=2))
print(json.dumps({'project':str(target),'backup':str(backup),'files_verified':len(observed),
 'baseline_verified':len(source_checks),'changed_files':len(changes)},indent=2))
'''.replace('PAYLOAD',repr(payload)).replace('MANIFEST',repr(files))
out=ROOT/'reports'/('deploy_reviewed'+('' if a.kind=='all' else '_'+a.kind)+'.py');out.parent.mkdir(exist_ok=True);out.write_text(code,encoding='utf-8')
if len(code.encode('utf-8'))>256*1024:raise RuntimeError('Audited tool script limit; use --kind code and --kind docs separately')
print(json.dumps({'script':str(out),'files':len(files),'payload_bytes':len(payload)}))
