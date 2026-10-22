import base64,json
from pathlib import Path
root=Path(__file__).resolve().parent
public='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKN4jo+x+B5xIl9nLTgX6jDniPsDFHjSKBzWRNhOmkzO sensor-migration-20261010-read-only'
reader=(root/'restricted_archive_reader.py').read_text()
source="from pathlib import Path\nimport os,json,hashlib\nw=Path('/root/gpufree-data/.migration_sensor_20261010_dual')\n"
source+="assert json.loads((w/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'\n"
source+="(w/'restricted_archive_reader.py').write_text("+repr(reader)+")\n"
source+="d=Path('/root/.ssh');created=not d.exists();d.mkdir(mode=0o700,exist_ok=True)\np=d/'authorized_keys'\nassert not p.is_symlink(),'Review authorized_keys symlink before modifying'\n"
source+="state=w/'source_key_change.json'\nassert not state.exists(),'Temporary key already installed; inspect before retry'\nold=p.read_bytes() if p.exists() else b''\n"
source+="line='restrict,command=\"/usr/bin/python3 -I -S -B /root/gpufree-data/.migration_sensor_20261010_dual/restricted_archive_reader.py\" '+"+repr(public)+"\n"
source+="new=old+(b'\\n' if old and not old.endswith(b'\\n') else b'')+line.encode()+b'\\n'\n"
source+="(w/'authorized_keys.before').write_bytes(old);os.chmod(w/'authorized_keys.before',0o600)\n"
source+="metadata={'original_exists':p.exists(),'directory_created':created,'original_mode':(p.stat().st_mode&0o777) if p.exists() else 0o600,'before_sha256':hashlib.sha256(old).hexdigest(),'after_sha256':hashlib.sha256(new).hexdigest(),'line':line}\n"
source+="state.write_text(json.dumps(metadata));temporary=d/'authorized_keys.sensor_migration.part'\nassert not temporary.exists(),'Temporary edit path conflict'\ntemporary.write_bytes(new);os.chmod(temporary,metadata['original_mode']);os.replace(temporary,p)\nprint(json.dumps({'read_only_key_installed':True,'before_sha256':metadata['before_sha256'],'after_sha256':metadata['after_sha256']}))\n"
(root/'source_install_read_key.py').write_text(source,encoding='utf-8')
target="from pathlib import Path\nimport base64,hashlib,json,subprocess,os\nw=Path('/root/gpufree-data/.migration_sensor_20261010_dual')\n"
target+="assert json.loads((w/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'\n"
for name in ('direct_download.py','validate_and_promote.py'):
    encoded=base64.b64encode((root/name).read_bytes()).decode();parts=[encoded[i:i+128] for i in range(0,len(encoded),128)]
    target+='b=base64.b64decode("".join('+repr(parts)+'));p=w/'+repr(name)+';p.write_bytes(b)\n'
target+="assert not (w/'direct_process.json').exists(),'Direct download already launched; inspect its status'\n"
target+="log=(w/'direct_download.log').open('ab');p=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(w/'direct_download.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);(w/'direct_process.json').write_text(json.dumps({'pid':p.pid}));print(json.dumps({'started':True,'pid':p.pid}))\n"
(root/'target_start_direct.py').write_text(target,encoding='utf-8')
print(json.dumps({'scripts':['source_install_read_key.py','target_start_direct.py']}))
