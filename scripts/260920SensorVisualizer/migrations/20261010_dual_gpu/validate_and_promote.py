"""Verify all staged bytes before non-overwriting promotion to the same paths."""
import hashlib,json,os,tarfile,time
from pathlib import Path,PurePosixPath
root=Path('/root/gpufree-data');work=root/'.migration_sensor_20261010_dual'
meta=json.loads((work/'archive_metadata.json').read_text());archive=work/'assets_and_code.tar.gz'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(4*1024*1024),b''):h.update(c)
    return h.hexdigest()
if archive.stat().st_size!=meta['archive_bytes'] or sha(archive)!=meta['archive_sha256']:raise RuntimeError('Archive integrity mismatch')
stage=work/'staging';stage.mkdir(mode=0o700,exist_ok=True);begin=time.monotonic();seen=set()
with tarfile.open(archive,'r:gz') as tf:
    # Read the manifest without trusting archive extraction paths.
    members=tf.getmembers();matches=[m for m in members if m.name=='migration_manifest.json']
    if len(matches)!=1 or not matches[0].isfile():raise RuntimeError('Missing or duplicate manifest')
    payload=tf.extractfile(matches[0]).read()
    if hashlib.sha256(payload).hexdigest()!=meta['manifest_sha256']:raise RuntimeError('Manifest integrity mismatch')
    manifest=json.loads(payload);expected={r['path']:r for r in manifest['files']}
    for m in members:
        if m.name=='migration_manifest.json':continue
        parts=PurePosixPath(m.name)
        if parts.is_absolute() or '..' in parts.parts or m.name not in expected or m.name in seen or not m.isfile():raise RuntimeError('Unexpected archive member')
        row=expected[m.name]
        if m.size!=row['size']:raise RuntimeError('Member size mismatch')
        p=stage/m.name
        if not p.resolve().is_relative_to(stage.resolve()):raise RuntimeError('Extraction escapes staging')
        p.parent.mkdir(parents=True,exist_ok=True)
        h=hashlib.sha256()
        with tf.extractfile(m) as src,p.open('wb') as dst:
            for c in iter(lambda:src.read(4*1024*1024),b''):dst.write(c);h.update(c)
        if h.hexdigest()!=row['sha256']:raise RuntimeError('File digest mismatch: '+m.name)
        os.chmod(p,row['mode']&0o777);os.utime(p,ns=(row['mtime_ns'],row['mtime_ns']));seen.add(m.name)
if seen!=set(expected):raise RuntimeError('Incomplete archive')
conflicts=[]
for name,row in expected.items():
    dst=root/name
    if not dst.resolve().is_relative_to(root.resolve()):raise RuntimeError('Destination escapes workspace')
    if dst.exists() and (not dst.is_file() or sha(dst)!=row['sha256']):conflicts.append(name)
if conflicts:raise RuntimeError('Existing destination differs; nothing promoted: '+repr(conflicts[:10]))
copied=identical=0
for name,row in expected.items():
    dst=root/name;src=stage/name;dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():identical+=1;continue
    # Same data filesystem; link creates the destination atomically without
    # replacing a file another task may have created after the conflict check.
    os.link(src,dst);copied+=1
for name,row in expected.items():
    if sha(root/name)!=row['sha256']:raise RuntimeError('Promoted digest mismatch')
(work/'migration_manifest.json').write_bytes(payload)
report={'passed':True,'files':len(expected),'source_bytes':manifest['bytes'],'copied':copied,
        'preexisting_identical':identical,'archive_sha256':meta['archive_sha256'],
        'all_file_sha256_match':True,'elapsed_s':time.monotonic()-begin,'same_root_paths':str(root)}
(work/'migration_result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
