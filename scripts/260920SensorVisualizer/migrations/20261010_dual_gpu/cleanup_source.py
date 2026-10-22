"""Delete this task's source-side archive after destination verification."""
import hashlib,json,shutil,time
from pathlib import Path
root=Path('/root/gpufree-data').resolve();work=root/'.migration_sensor_20261010_dual'
assert work.resolve().parent==root and not work.is_symlink()
assert json.loads((work/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'
revoked=json.loads((work/'source_key_cleanup.json').read_text())
assert revoked['task_key_removed'] and revoked['original_restored_exactly']
assert hashlib.sha256(Path('/root/.ssh/authorized_keys').read_bytes()).hexdigest()==revoked['after_sha256']
meta=json.loads((work/'archive_metadata.json').read_text())
assert meta['archive_sha256']=='693288517fa655f7f1d136f560213734f01de2bcda7258d27092b6e030d2bdc3'
removed=[];removed_bytes=0
for name in ('assets_and_code.tar.gz','restricted_archive_reader.py','authorized_keys.before'):
    p=work/name
    if not p.exists():continue
    assert p.parent.resolve()==work.resolve() and p.is_file() and not p.is_symlink()
    if name=='assets_and_code.tar.gz':
        h=hashlib.sha256()
        with p.open('rb') as f:
            for c in iter(lambda:f.read(4*1024*1024),b''):h.update(c)
        assert h.hexdigest()==meta['archive_sha256']
    removed_bytes+=p.stat().st_size;p.unlink();removed.append(name)
report={'passed':True,'removed':removed,'transport_bytes_removed':removed_bytes,
        'authorized_keys_restored':True,'source_assets_and_code_unchanged':True,
        'free_bytes':shutil.disk_usage(root).free,'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
(work/'source_cleanup.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
