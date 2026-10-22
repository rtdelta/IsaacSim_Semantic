"""Build a reviewed stdlib deployment for ops.py; destination is v02 only."""
from pathlib import Path
import base64
import hashlib
import io
import json
import zipfile

root = Path(__file__).resolve().parents[1]
files = {}
memory = io.BytesIO()
with zipfile.ZipFile(memory, 'w', zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        if not p.is_file() or any(part in ('__pycache__', 'reports', 'generated', '.pytest_cache') for part in rel.parts):
            continue
        if p.suffix not in ('.py', '.json', '.md', '.toml', '.kit', '.txt'):
            continue
        data = p.read_bytes()
        files[rel.as_posix()] = hashlib.sha256(data).hexdigest()
        archive.writestr(rel.as_posix(), data)
payload = base64.b64encode(memory.getvalue()).decode('ascii')
script = '''from pathlib import Path, PurePosixPath
import base64, hashlib, io, json, zipfile, datetime
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
parent = root.parent.resolve(strict=True)
if root.is_symlink() or parent != Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer'):
    raise RuntimeError('Unexpected project destination')
root.mkdir(exist_ok=True)
manifest = MANIFEST
previous_path = root/'deployment_manifest.json'
previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD)))
backup = root/'deploy_history'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
changed = []
for name in archive.namelist():
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or name not in manifest:
        raise ValueError('Unsafe deployment path')
    dest = root.joinpath(*rel.parts)
    if not dest.resolve().is_relative_to(root):
        raise ValueError('Deployment escapes v02')
    data = archive.read(name)
    if hashlib.sha256(data).hexdigest() != manifest[name]:
        raise ValueError('Deployment hash mismatch')
    if dest.exists():
        existing = hashlib.sha256(dest.read_bytes()).hexdigest()
        if existing == manifest[name]: continue
        if previous.get(name) != existing:
            raise RuntimeError('Remote file has untracked edits: '+name)
    changed.append((name, dest, data))
for name, dest, data in changed:
    if dest.exists():
        old = backup/name
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(dest.read_bytes())
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name+'.deploying')
    temp.write_bytes(data)
    temp.replace(dest)
previous_path.write_text(json.dumps(manifest, indent=2)+'\\n')
print(json.dumps({'root':str(root), 'files':len(manifest), 'changed':len(changed), 'backup':str(backup) if backup.exists() else None}))
'''.replace('MANIFEST', repr(files)).replace('PAYLOAD', repr(payload))
(root/'generated').mkdir(exist_ok=True)
(root/'generated/deploy.py').write_text(script, encoding='utf-8')
(root/'generated/local_manifest.json').write_text(json.dumps(files, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'files': len(files), 'archive_bytes': len(memory.getvalue()), 'script': str(root/'generated/deploy.py')}))
