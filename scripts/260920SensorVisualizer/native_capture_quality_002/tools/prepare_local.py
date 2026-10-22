"""Make recoverable source snapshots and independent experimental source copies."""
import hashlib,json,shutil,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];parent=root.parent
root.joinpath('reports').mkdir(exist_ok=True)
backup=root/'backups/20261012_pre_NC002_sources.zip';backup.parent.mkdir(exist_ok=True)
manifest={}
for name in ('native_capture_baseline','v06','single06_lab'):
 for p in sorted((parent/name).rglob('*')):
  if not p.is_file() or any(x in p.relative_to(parent/name).parts for x in ('reports','__pycache__','deploy_history','backups')):continue
  manifest[p.relative_to(parent).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
if not backup.exists():
 with zipfile.ZipFile(backup,'x',zipfile.ZIP_DEFLATED) as z:
  for rel in manifest:z.write(parent/rel,rel)
 (root/'reports/preserved_source_hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
else:
 original=json.loads((root/'reports/preserved_source_hashes.json').read_text())
 if original!=manifest:raise RuntimeError('Original source changed since snapshot')
for rel in ('run.py','kit_entry.py','tools/validate_bag.py','tools/analyze_results.py','tools/pull_evidence.py','config/baseline.json'):
 dst=root/rel;dst.parent.mkdir(exist_ok=True)
 if not dst.exists():shutil.copyfile(parent/'native_capture_baseline'/rel,dst)
plan=parent/'docs/NC-002_20261012_NativeCaptureQualityAndCost_Implementation.md'
root.joinpath('docs').mkdir(exist_ok=True)
shutil.copyfile(plan,root/'docs/NC-002_implementation_plan.md')
print(json.dumps({'snapshot':str(backup),'preserved_files':len(manifest),'project':str(root)}))
