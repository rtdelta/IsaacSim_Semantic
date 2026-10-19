"""Package only this project; the reviewed remote script preserves remote edits."""
from pathlib import Path
import base64,hashlib,io,json,zipfile

root=Path(__file__).resolve().parents[1];files={};items=[]
for path in sorted(root.rglob('*')):
    relative=path.relative_to(root)
    if not path.is_file() or any(p in ('__pycache__','reports','generated','deploy_history','.git') for p in relative.parts):continue
    if path.suffix not in ('.py','.json','.md','.txt','.toml') and not (path.suffix in ('.png','.jpg') and relative.parts[:2]==('docs','evidence')):continue
    data=path.read_bytes();files[relative.as_posix()]=hashlib.sha256(data).hexdigest()
    items.append((relative.as_posix(),data))

def package(entries):
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in entries:archive.writestr(name,data)
    return memory.getvalue()

# The audited executor has a 256 KiB reviewed-script limit. Transfer whole
# project files in independently verified, small packages instead of raising it.
batches=[];batch=[]
for entry in items:
    candidate=batch+[entry]
    if batch and len(package(candidate))>140000:
        batches.append(batch);batch=[entry]
    else:batch=candidate
if batch:batches.append(batch)
template='''from pathlib import Path, PurePosixPath
import base64,hashlib,io,json,zipfile,datetime
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
if root.is_symlink() or root.parent.resolve(strict=True)!=root.parent:
    raise RuntimeError('Unexpected destination or symlink')
root.mkdir(exist_ok=True)
manifest=MANIFEST
previous_path=root/'deployment_manifest.json'
previous=json.loads(previous_path.read_text()) if previous_path.is_file() else {}
archive=zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD)))
backup=root/'deploy_history'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
changed=[]
for name in archive.namelist():
    relative=PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or name not in manifest:raise ValueError('Unsafe name')
    dest=root.joinpath(*relative.parts)
    if dest.is_symlink() or not dest.resolve().is_relative_to(root):raise ValueError('Escaping destination')
    data=archive.read(name)
    if hashlib.sha256(data).hexdigest()!=manifest[name]:raise ValueError('Payload hash mismatch')
    if dest.exists():
        existing=hashlib.sha256(dest.read_bytes()).hexdigest()
        if existing==manifest[name]:continue
        if previous.get(name)!=existing:raise RuntimeError('Untracked remote edit: '+name)
    changed.append((name,dest,data))
for name,dest,data in changed:
    if dest.exists():
        old=backup/name;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(dest.read_bytes())
    dest.parent.mkdir(parents=True,exist_ok=True)
    temporary=dest.with_name(dest.name+'.deploying');temporary.write_bytes(data);temporary.replace(dest)
merged=dict(previous);merged.update(manifest)
previous_path.write_text(json.dumps(merged,indent=2)+'\\n')
mismatch=[n for n,h in manifest.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
print(json.dumps({'root':str(root),'files':len(manifest),'changed':len(changed),'mismatch':mismatch,
                  'backup':str(backup) if backup.exists() else None}))
if mismatch:raise RuntimeError('Post-deployment verification failed')
'''
(root/'generated').mkdir(exist_ok=True)
scripts=[];total=0
for i,batch in enumerate(batches,1):
    data=package(batch);total+=len(data)
    subset={name:files[name] for name,_ in batch}
    script=template.replace('MANIFEST',repr(subset)).replace('PAYLOAD',repr(base64.b64encode(data).decode('ascii')))
    if len(script.encode('utf-8'))>256*1024:raise ValueError('A single file exceeds audited transfer size; use reviewed SFTP transfer')
    path=root/f'generated/deploy_{i:02d}.py';path.write_text(script,encoding='utf-8')
    scripts.append(str(path))
(root/'generated/local_manifest.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
(root/'generated/deployment_batches.json').write_text(json.dumps({'files':len(files),'scripts':scripts},indent=2))
print(json.dumps({'files':len(files),'archive_bytes':total,'scripts':scripts}))
