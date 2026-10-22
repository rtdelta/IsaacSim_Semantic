"""Remove only validated task-owned transport files; leave final project intact."""
import hashlib,json,os,shutil,time
from pathlib import Path
root=Path('/root/gpufree-data').resolve();work=root/'.migration_sensor_20261010_dual'
assert work.resolve().parent==root and not work.is_symlink()
assert json.loads((work/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'
result=json.loads((work/'migration_result.json').read_text())
assert result['passed'] and result['all_file_sha256_match'] and result['files']==1663
active=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        c=p.read_bytes().replace(b'\0',b' ').decode(errors='replace')
        if str(work) in c and ('direct_download.py' in c or 'validate_and_promote.py' in c or 'assets_and_code.tar.gz.part' in c):active.append(str(p.parent))
    except (FileNotFoundError,PermissionError,ProcessLookupError):pass
assert not active, active
removed=[];removed_bytes=0
def remove(name):
    global removed_bytes
    p=work/name
    if not p.exists():return
    assert p.parent.resolve()==work.resolve() and p.is_file() and not p.is_symlink()
    removed_bytes+=p.stat().st_size;p.unlink();removed.append(name)
# The source has already revoked the forced-read public key.
remove('source_read_key');remove('source_read_key.pub')
archive=work/'assets_and_code.tar.gz'
if archive.exists():
    h=hashlib.sha256()
    with archive.open('rb') as f:
        for c in iter(lambda:f.read(4*1024*1024),b''):h.update(c)
    assert h.hexdigest()==result['archive_sha256']
    remove(archive.name)
for name in ('assets_and_code.tar.gz.part','assets_and_code.direct.tar.gz.part'):remove(name)
stage=work/'staging'
if stage.exists():
    assert stage.resolve()==work.resolve()/'staging' and not stage.is_symlink()
    rows=json.loads((work/'migration_manifest.json').read_text())['files']
    expected={r['path'] for r in rows};actual=set()
    for base,dirs,files in os.walk(stage,followlinks=False):
        for name in dirs+files:assert not (Path(base)/name).is_symlink()
        for name in files:actual.add((Path(base)/name).relative_to(stage).as_posix())
    assert actual==expected
    for name in expected:
        a=(stage/name).stat();b=(root/name).stat()
        assert (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) and b.st_nlink>=2
    shutil.rmtree(stage);removed.append('staging (verified hard links only)')
report={'passed':True,'removed':removed,'transport_bytes_removed':removed_bytes,
        'private_transport_key_absent':not (work/'source_read_key').exists(),
        'active_owned_transfer_processes':active,'final_files_preserved':1663,
        'free_bytes':shutil.disk_usage(root).free,'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
(work/'target_cleanup.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
