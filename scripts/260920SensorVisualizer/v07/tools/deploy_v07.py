"""Audited deployment of local project files; preserve v06 and changed v07 files."""
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import uuid
import zipfile
import paramiko
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit,verify_file
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python

root=Path(__file__).resolve().parents[1];project=root.parent
profile=project/'migrations/20261010_dual_gpu/targets.json'
target=json.loads(profile.read_text())['targets']['isaac-dual']
reports=root/'reports/deployment';reports.mkdir(parents=True,exist_ok=True)
files=[p for p in root.rglob('*') if p.is_file() and not set(p.relative_to(root).parts)&{'reports','__pycache__'}
       and p.suffix not in ('.pyc','.pyo') and p.name!='deployment_manifest.json']
manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
archive=reports/('v07_'+uuid.uuid4().hex+'.zip')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(root).as_posix())
secret=WindowsCredentials().read(target['credential_ref']);redactor=Redactor([secret])
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,
            'sensor-v07-implementation','Deploy independent v07 source and retain restorable code baselines',
            'audited-sftp-code-deploy',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient();transport=None;sftp=None
def run(script,label,timeout=30):
    redactor.reject_sensitive_text(script,'Remote deployment script');audit.snapshot(label,script)
    result=remote_python(client,script,audit,label,timeout)
    if result['exit_code']:raise RuntimeError(label+' failed: '+redactor.text(result['stderr']))
    return json.loads(result['stdout'])
try:
    audit.event('ssh.connect.requested',target_alias='isaac-dual',host=target['host'],port=target['port'],declared_intent='write')
    transport=paramiko.Transport(socket.create_connection((target['host'],target['port']),timeout=15));transport.start_client(timeout=15)
    check_fingerprint(transport.get_remote_server_key(),target['host_fingerprint']);audit.event('ssh.host_key.verified',fingerprint=target['host_fingerprint'])
    transport.auth_timeout=15;transport.auth_password(target['username'],secret);secret=None;client._transport=transport
    audit.event('ssh.authenticated',target_alias='isaac-dual')
    actual=run("import hashlib,json,os\nfrom pathlib import Path\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()}))\n",'identity')
    check_identity(actual,target);audit.event('ssh.instance.verified',**actual)
    base='/root/gpufree-data/semantic/scripts/260920SensorVisualizer'
    history=base+'/deploy_history/v07/'+audit.id
    preflight='''import json,hashlib,zipfile
from pathlib import Path
root=Path(ROOT);assert root.resolve()==root and root.is_dir()
history=root/'deploy_history/v07'/OPERATION;history.mkdir(parents=True,exist_ok=False)
baseline=EXPECTED_BASELINE
source=root/'v06'
for name,digest in baseline.items():
    assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,'v06 changed: '+name
backup=root/'backups'/('v07_'+OPERATION);backup.mkdir(parents=True)
with zipfile.ZipFile(backup/'v06_source.zip','x',zipfile.ZIP_DEFLATED) as z:
    for name in baseline:z.write(source/name,name)
(backup/'v06_manifest.json').write_text(json.dumps(baseline,indent=2))
print(json.dumps({'history':str(history),'v06_backup':str(backup),'files':len(baseline)}))
'''.replace('ROOT',repr(base)).replace('OPERATION',repr(audit.id)).replace('EXPECTED_BASELINE',repr(json.loads((root/'baseline_manifest.json').read_text())['sha256']))
    baseline=run(preflight,'baseline-and-preflight')
    sftp=paramiko.SFTPClient.from_transport(transport);sftp.get_channel().settimeout(30)
    remote_zip=history+'/source.zip'
    audit.event('sftp.upload.requested',local_path=str(archive),remote_path=remote_zip,bytes=archive.stat().st_size,
                sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    sftp.put(str(archive),remote_zip)
    audit.event('sftp.upload.completed',remote_path=remote_zip)
    script='''import hashlib,json,os,zipfile,uuid
from pathlib import Path
root=Path(ROOT);destination=root/'v07';assert destination.resolve()==destination
history=Path(HISTORY);archive=history/'source.zip';assert hashlib.sha256(archive.read_bytes()).hexdigest()==ARCHIVE_SHA
manifest=MANIFEST
previous=json.loads((destination/'deployment_manifest.json').read_text()) if (destination/'deployment_manifest.json').exists() else {}
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==set(manifest)
    changed=[]
    for name,digest in manifest.items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        data=z.read(name);assert hashlib.sha256(data).hexdigest()==digest
        path=destination/name;assert path.resolve()==path and not path.is_symlink()
        if path.exists():
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual==digest or previous.get(name)==actual,'User-modified v07 file: '+name
            if actual!=digest:changed.append(name)
    if changed:
        with zipfile.ZipFile(history/'previous_v07.zip','x',zipfile.ZIP_DEFLATED) as old:
            for name in changed:old.write(destination/name,name)
    for name,digest in manifest.items():
        path=destination/name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest:continue
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_bytes(z.read(name));temp.replace(path)
        finally:temp.unlink(missing_ok=True)
    for name,digest in manifest.items():assert hashlib.sha256((destination/name).read_bytes()).hexdigest()==digest
(destination/'deployment_manifest.json').write_text(json.dumps(manifest,indent=2))
result={'passed':True,'project':str(destination),'files':len(manifest),'changed_v07_files':changed,'v06_unchanged':True,'operation':OPERATION}
(history/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
'''.replace('ROOT',repr(base)).replace('HISTORY',repr(history)).replace('ARCHIVE_SHA',repr(hashlib.sha256(archive.read_bytes()).hexdigest())).replace('MANIFEST',repr(manifest)).replace('OPERATION',repr(audit.id))
    result=run(script,'extract-and-verify')
    (reports/'latest.json').write_text(json.dumps({**result,'baseline':baseline,'audit_log':str(audit.path)},indent=2),encoding='utf-8')
    (root/'deployment_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    audit.finish('succeeded',**result)
    assert verify_file(audit.path)['integrity']=='valid'
    print(json.dumps(result))
except Exception as exc:
    if not audit.closed:audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)))
    raise
finally:
    if sftp:sftp.close()
    client.close()
    if transport:transport.close()
