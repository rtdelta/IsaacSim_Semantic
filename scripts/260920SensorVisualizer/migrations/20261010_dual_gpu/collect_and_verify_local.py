"""Read migrated metadata and compare active code with trusted local sources."""
import hashlib,json,os,sys
from pathlib import Path
import paramiko
skill=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts');sys.path.insert(0,str(skill))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python
root=Path(__file__).resolve().parent;profile=root/'targets.json';target=json.loads(profile.read_text())['targets']['isaac-dual']
value=WindowsCredentials().read(target['credential_ref']);redactor=Redactor([value])
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,
    'dual-gpu-code-provenance','读取目标迁移清单并对照本地可信v06与v05基线','read-and-verify',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient();t=None
try:
    t=paramiko.Transport((target['host'],target['port']));t.start_client(timeout=15);check_fingerprint(t.get_remote_server_key(),target['host_fingerprint']);t.auth_password(target['username'],value);value=None;client._transport=t
    identity=remote_python(client,"import hashlib,json,os\nfrom pathlib import Path\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()}))\n",audit,'target-identity',30)
    check_identity(json.loads(identity['stdout']),target)
    sftp=paramiko.SFTPClient.from_transport(t);work='/root/gpufree-data/.migration_sensor_20261010_dual/'
    for name in ('migration_result.json','migration_manifest.json','direct_status.json'):
        with sftp.open(work+name,'r') as f:data=f.read()
        (root/name).write_bytes(data)
    with sftp.open('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/deployment_manifest.json','r') as f:manifest=json.loads(f.read())
    rows={r['path']:r for r in json.loads((root/'migration_manifest.json').read_bytes())['files']};local=root.parent.parent/'v06';bad=[]
    for n,h in manifest.items():
        name='semantic/scripts/260920SensorVisualizer/v06/'+n
        if rows.get(name,{}).get('sha256')!=h or hashlib.sha256((local/n).read_bytes()).hexdigest()!=h:bad.append(n)
    baseline=json.loads((local/'baseline_manifest.json').read_text())['sha256'];old_bad=[n for n,h in baseline.items() if rows.get('semantic/scripts/260920SensorVisualizer/v05/'+n,{}).get('sha256')!=h]
    if bad or old_bad:raise RuntimeError('Source identity mismatch')
    report={'v06_local_matching_files':len(manifest),'v06_mismatches':bad,'v05_baseline_matching_files':len(baseline),'v05_mismatches':old_bad}
    (root/'code_provenance.json').write_text(json.dumps(report,indent=2));audit.event('code.provenance.verified',**report);audit.finish('succeeded');print(json.dumps(report))
except Exception as exc:
    audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
finally:
    client.close()
    if t:t.close()
