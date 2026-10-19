import hashlib,json,subprocess
from pathlib import Path
work=Path('/root/gpufree-data/.migration_sensor_20261010_dual')
assert json.loads((work/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'
key=work/'source_read_key'
if not key.exists():subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key),'-C','sensor-migration-20261010-read-only'],check=True)
scan=subprocess.run(['ssh-keyscan','-T','5','-t','ed25519','100.122.231.122'],capture_output=True,text=True,check=True)
hosts=work/'source_known_hosts';hosts.write_text(scan.stdout)
fp=subprocess.run(['ssh-keygen','-lf',str(hosts)],capture_output=True,text=True,check=True).stdout
expected='SHA256:kIfeVQ2EQsdiXEPSocGzqmCzv3sOWkAQPMRY8owqnbU'
assert expected in fp,'Private route host key differs from pinned source host'
print(json.dumps({'public_key':Path(str(key)+'.pub').read_text().strip(),'source_fingerprint':expected,
                 'known_hosts_sha256':hashlib.sha256(hosts.read_bytes()).hexdigest()}))
