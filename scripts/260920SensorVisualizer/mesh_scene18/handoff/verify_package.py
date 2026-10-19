"""Verify handoff bytes with standard-library Python; never modifies any file."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root/'package_manifest.json').read_text(encoding='utf-8'))
errors = []
for row in manifest['files']:
    path = root/row['path']
    if not path.resolve().is_relative_to(root):
        errors.append({'path':row['path'],'error':'invalid path'}); continue
    if not path.is_file():
        errors.append({'path':row['path'],'error':'missing'}); continue
    if path.stat().st_size != row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        errors.append({'path':row['path'],'error':'hash or size mismatch'})
print(json.dumps({'passed':not errors,'checked_files':len(manifest['files']),'errors':errors},indent=2))
raise SystemExit(1 if errors else 0)
