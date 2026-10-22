"""Authenticate with a credential reference and record actual new identity."""
import hashlib,json,os,sys
from pathlib import Path
import paramiko
skill=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
sys.path.insert(0,str(skill))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,remote_python
root=Path(__file__).resolve().parent
config=root/'targets.json';policy=json.loads(config.read_text());target=policy['targets']['isaac-dual']
redactor=Redactor();value=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(value)
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,
    'dual-gpu-identity','固定主机指纹后核实双卡实例身份与容量','first-identity',hashlib.sha256(config.read_bytes()).hexdigest())
client=paramiko.SSHClient();transport=None
try:
    audit.event('ssh.connection.requested',host=target['host'],port=target['port'],username=target['username'],auth='credential-reference')
    transport=paramiko.Transport((target['host'],target['port']));transport.start_client(timeout=15)
    check_fingerprint(transport.get_remote_server_key(),target['host_fingerprint'])
    audit.event('ssh.host_key.verified',fingerprint=target['host_fingerprint'],trust='first-observation pinned, not independent platform attestation')
    transport.auth_password(target['username'],value);value=None;client._transport=transport
    script="import os,json,hashlib,subprocess,shutil\nfrom pathlib import Path\nr=Path('/root/gpufree-data')\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest(),'disk':dict(zip(('total','used','free'),shutil.disk_usage(r))),'root_entries':[p.name for p in r.iterdir()],'gpu':subprocess.run(['nvidia-smi','--query-gpu=index,uuid,name,memory.total','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()}))\n"
    result=remote_python(client,script,audit,'new-identity',30)
    if result['exit_code']:raise RuntimeError('Identity probe failed')
    identity=json.loads(result['stdout']);target.update(hostname=identity['hostname'],machine_id_sha256=identity['machine_id_sha256'],identity_recorded='2026-10-10; pinned first-contact host key, actual machine identity; no independent platform attestation')
    config.write_text(json.dumps(policy,indent=2),encoding='utf-8')
    (root/'new_identity.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
    audit.event('instance.identity.recorded',**identity);audit.finish('succeeded')
    print(json.dumps({'connected':True,'identity':identity,'audit_log':str(audit.path)}))
except Exception as exc:
    audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)))
    print(json.dumps({'connected':False,'error_type':type(exc).__name__,'error':redactor.text(str(exc))}))
finally:
    client.close()
    if transport:transport.close()
