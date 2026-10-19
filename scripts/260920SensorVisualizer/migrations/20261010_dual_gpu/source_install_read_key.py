from pathlib import Path
import os,json,hashlib
w=Path('/root/gpufree-data/.migration_sensor_20261010_dual')
assert json.loads((w/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'
(w/'restricted_archive_reader.py').write_text('"""Forced SSH command: only probe or read this immutable migration archive."""\nimport hashlib,json,os,sys\nfrom pathlib import Path\nwork=Path(\'/root/gpufree-data/.migration_sensor_20261010_dual\')\nmeta=json.loads((work/\'archive_metadata.json\').read_text())\ncommand=os.environ.get(\'SSH_ORIGINAL_COMMAND\',\'\')\nif command==\'probe\':\n    print(json.dumps({\'task\':\'sensor-visualizer-dual-migration-20261010\',**meta}));sys.exit(0)\nif command!=\'read\':sys.exit(64)\np=work/\'assets_and_code.tar.gz\'\nif p.stat().st_size!=meta[\'archive_bytes\']:sys.exit(65)\nwith p.open(\'rb\') as f:\n    for c in iter(lambda:f.read(1048576),b\'\'):sys.stdout.buffer.write(c)\nsys.stdout.buffer.flush()\n')
d=Path('/root/.ssh');created=not d.exists();d.mkdir(mode=0o700,exist_ok=True)
p=d/'authorized_keys'
assert not p.is_symlink(),'Review authorized_keys symlink before modifying'
state=w/'source_key_change.json'
assert not state.exists(),'Temporary key already installed; inspect before retry'
old=p.read_bytes() if p.exists() else b''
line='restrict,command="/usr/bin/python3 -I -S -B /root/gpufree-data/.migration_sensor_20261010_dual/restricted_archive_reader.py" '+'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKN4jo+x+B5xIl9nLTgX6jDniPsDFHjSKBzWRNhOmkzO sensor-migration-20261010-read-only'
new=old+(b'\n' if old and not old.endswith(b'\n') else b'')+line.encode()+b'\n'
(w/'authorized_keys.before').write_bytes(old);os.chmod(w/'authorized_keys.before',0o600)
metadata={'original_exists':p.exists(),'directory_created':created,'original_mode':(p.stat().st_mode&0o777) if p.exists() else 0o600,'before_sha256':hashlib.sha256(old).hexdigest(),'after_sha256':hashlib.sha256(new).hexdigest(),'line':line}
state.write_text(json.dumps(metadata));temporary=d/'authorized_keys.sensor_migration.part'
assert not temporary.exists(),'Temporary edit path conflict'
temporary.write_bytes(new);os.chmod(temporary,metadata['original_mode']);os.replace(temporary,p)
print(json.dumps({'read_only_key_installed':True,'before_sha256':metadata['before_sha256'],'after_sha256':metadata['after_sha256']}))
