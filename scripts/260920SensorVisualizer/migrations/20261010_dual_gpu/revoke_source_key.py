import hashlib,json,os
from pathlib import Path
work=Path('/root/gpufree-data/.migration_sensor_20261010_dual')
state=json.loads((work/'source_key_change.json').read_text());p=Path('/root/.ssh/authorized_keys')
assert not p.is_symlink(),'Authorized keys path changed'
current=p.read_bytes();backup=(work/'authorized_keys.before').read_bytes()
assert hashlib.sha256(backup).hexdigest()==state['before_sha256'],'Backup mismatch'
unchanged=hashlib.sha256(current).hexdigest()==state['after_sha256']
if unchanged:
    if state['original_exists']:
        temporary=p.with_name('authorized_keys.sensor_migration_cleanup.part');temporary.write_bytes(backup);os.chmod(temporary,state['original_mode']);os.replace(temporary,p)
    else:p.unlink()
else:
    lines=current.splitlines(keepends=True);filtered=b''.join(line for line in lines if line.rstrip(b'\r\n')!=state['line'].encode())
    assert filtered!=current,'Task key not found; inspect changed authorized_keys'
    temporary=p.with_name('authorized_keys.sensor_migration_cleanup.part');temporary.write_bytes(filtered);os.chmod(temporary,p.stat().st_mode&0o777);os.replace(temporary,p)
after=p.read_bytes() if p.exists() else b''
assert state['line'].encode() not in after,'Task key still present'
report={'task_key_removed':True,'original_restored_exactly':hashlib.sha256(after).hexdigest()==state['before_sha256'],
        'other_changes_preserved':not unchanged,'after_sha256':hashlib.sha256(after).hexdigest()}
(work/'source_key_cleanup.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
