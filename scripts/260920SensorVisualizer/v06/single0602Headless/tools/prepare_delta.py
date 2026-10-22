"""Build small audited deployment batches for explicitly named project files."""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
paths = sorted({(ROOT/name).resolve() for name in sys.argv[1:]})
assert paths and all(p.is_file() and p.is_relative_to(ROOT) for p in paths)
batch = []
parts = []
def pack(items):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for p in items:
            archive.writestr(p.relative_to(ROOT).as_posix(), p.read_bytes())
    return stream.getvalue()
for p in paths:
    if batch and len(pack(batch+[p])) > 120_000:
        parts.append(batch); batch = []
    batch.append(p)
if batch:
    parts.append(batch)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
for index, items in enumerate(parts):
    raw = pack(items)
    digest = hashlib.sha256(raw).hexdigest()
    script = '''import base64,hashlib,io,json,zipfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
assert root.is_dir() and root.resolve()==root
raw=base64.b64decode(PAYLOAD)
assert hashlib.sha256(raw).hexdigest()==DIGEST
backup=root/'reports/deployment_backups'/STAMP
changed=[]
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    for item in archive.infolist():
        path=root/item.filename
        assert path.resolve().is_relative_to(root) and not path.is_symlink()
        data=archive.read(item)
        if path.is_file() and path.read_bytes()==data:continue
        if path.exists():
            saved=backup/item.filename;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(path.read_bytes())
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==hashlib.sha256(data).hexdigest()
        changed.append(item.filename)
print(json.dumps({'changed':changed,'backup':str(backup),'sha256':DIGEST}))
'''.replace('PAYLOAD', repr(base64.b64encode(raw).decode())).replace('DIGEST', repr(digest)).replace('STAMP', repr(stamp))
    target = ROOT/'reports'/('delta_%s_%02d.py' % (stamp, index))
    target.write_text(script, encoding='utf-8')
    print(json.dumps({'script': str(target), 'files': len(items), 'bytes': len(script.encode())}))
