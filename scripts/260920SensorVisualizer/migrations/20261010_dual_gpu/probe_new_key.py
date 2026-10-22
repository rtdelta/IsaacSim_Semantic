"""First-contact key probe; only the existing project key is attempted.

New host key is observed TOFU, saved before authentication; it is not an
independent platform attestation. No password or private key is output.
"""
import hashlib,json,sys
from pathlib import Path
import paramiko
skill=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
sys.path.insert(0,str(skill))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,private_directory
from cloud_ops.ssh import key_fingerprint,remote_python
import os
root=Path(__file__).resolve().parent
state=private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps')
policy_path=skill/'config.json'
audit=Audit(state,Redactor(),'dual-gpu-first-contact','核实新双卡实例身份并尝试既有项目公钥','first-contact',hashlib.sha256(policy_path.read_bytes()).hexdigest())
client=paramiko.SSHClient()
transport=None
try:
    audit.event('ssh.connection.requested',host='120.209.70.195',port=30716,username='root',auth='existing-project-key',fingerprint_provenance='first_observation_TOFU')
    transport=paramiko.Transport(('120.209.70.195',30716));transport.start_client(timeout=15)
    observed=key_fingerprint(transport.get_remote_server_key())
    record={'host':'120.209.70.195','port':30716,'host_fingerprint':observed,'trust':'TOFU; no independent platform fingerprint supplied'}
    saved=root/'new_host_observation.json'
    if saved.exists() and json.loads(saved.read_text())['host_fingerprint']!=observed:
        raise RuntimeError('Previously observed new-instance fingerprint changed')
    saved.write_text(json.dumps(record,indent=2),encoding='utf-8')
    audit.event('ssh.host_key.observed',**record)
    key=paramiko.Ed25519Key.from_private_key_file('C:/Users/15452/.ssh/id_ed25519_isaacsim_gpufree')
    transport.auth_publickey('root',key)
    if not transport.is_authenticated():raise RuntimeError('Project public key rejected')
    client._transport=transport
    result=remote_python(client,"import os,json,hashlib,subprocess,shutil\nfrom pathlib import Path\nr=Path('/root/gpufree-data')\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest(),'disk':dict(zip(('total','used','free'),shutil.disk_usage(r))),'root_entries':[p.name for p in r.iterdir()],'gpu':subprocess.run(['nvidia-smi','--query-gpu=index,uuid,name,memory.total','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()}))\n",audit,'first-identity',30)
    if result['exit_code']:raise RuntimeError('Identity probe failed')
    record.update(json.loads(result['stdout']));record['public_key_authenticated']=True
    (root/'new_identity.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    policy=json.loads(policy_path.read_text());policy['targets']['isaac-dual']={
        'host':'120.209.70.195','port':30716,'username':'root','auth':'key',
        'identity_file':'C:/Users/15452/.ssh/id_ed25519_isaacsim_gpufree',
        'host_fingerprint':observed,'hostname':record['hostname'],
        'machine_id_sha256':record['machine_id_sha256'],'workspace':'/root/gpufree-data',
        'identity_recorded':'2026-10-10; first-contact TOFU and project public key; no platform attestation'}
    (root/'targets.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    audit.finish('succeeded');print(json.dumps({'connected':True,'identity':record,'audit_log':str(audit.path)}))
except Exception as exc:
    audit.finish('failed',error_type=type(exc).__name__,error=str(exc))
    print(json.dumps({'connected':False,'error_type':type(exc).__name__,'error':str(exc),'audit_log':str(audit.path)}))
finally:
    client.close()
    if transport:transport.close()
