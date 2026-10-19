"""Prepare a self-generated, hash-checked deployment script for the audited SSH runner."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
from project_files import delivery_files

ROOT=Path(__file__).resolve().parents[1]
files=list(delivery_files(ROOT, include_manifest=True))
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in files:archive.writestr(path.relative_to(ROOT).as_posix(),path.read_bytes())
raw=stream.getvalue()
script='''import base64,hashlib,io,json,zipfile
from pathlib import Path
from datetime import datetime,timezone
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
root.mkdir(parents=True,exist_ok=True)
assert root.resolve()==root and not root.is_symlink()
raw=base64.b64decode(DATA)
assert hashlib.sha256(raw).hexdigest()==DIGEST
backup=root/'reports/deployment_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
count=0
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    for item in archive.infolist():
        path=root/item.filename
        if not path.resolve().is_relative_to(root) or path.is_symlink():raise ValueError('Invalid deployment path')
        data=archive.read(item)
        if path.is_file() and path.read_bytes()==data:continue
        if path.exists():
            saved=backup/item.filename;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(path.read_bytes())
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==hashlib.sha256(data).hexdigest()
        count+=1
print(json.dumps({'state':'deployed','files_changed':count,'archive_sha256':DIGEST,'backup':str(backup),'root':str(root)}))
'''.replace('DATA',repr(base64.b64encode(raw).decode())).replace('DIGEST',repr(hashlib.sha256(raw).hexdigest()))
target=ROOT/'reports/deploy_remote.py';target.parent.mkdir(exist_ok=True)
target.write_text(script,encoding='utf-8')
print(json.dumps({'script':str(target),'bytes':len(script.encode()),'files':len(files),'archive_sha256':hashlib.sha256(raw).hexdigest()}))
