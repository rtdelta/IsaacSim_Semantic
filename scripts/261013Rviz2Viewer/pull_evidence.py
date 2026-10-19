"""Retrieve small task-owned evidence with identity pinning and SHA-256 checks."""
import datetime,hashlib,json,os,sys,warnings
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore');import paramiko
profile=ROOT.parent/'260920SensorVisualizer/migrations/20261010_dual_gpu/targets.json'
target=json.loads(profile.read_text())['targets']['isaac-new'];redactor=Redactor()
kwargs=dict(hostname=target['host'],port=target['port'],username=target['username'],look_for_keys=False,allow_agent=False,timeout=20,banner_timeout=20,auth_timeout=20)
if target['auth']=='windows-credential':
    value=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(value);kwargs['password']=value
elif target['auth']=='key':kwargs['key_filename']=target['identity_file']
else:raise ValueError('Unsupported credential reference')
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'20261013-rviz-viewer-300','Retrieve task evidence only, without transferring whole MCAP','project-evidence-sftp',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient()
class Pin(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self,client,hostname,key):check_fingerprint(key,target['host_fingerprint']);audit.event('ssh.host_key.verified',target_alias='isaac-new')
client.set_missing_host_key_policy(Pin())
script="""import hashlib,json
from pathlib import Path
r=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer/reports')
names=['evidence_summary.json','rviz_frame150.png','rviz_isolated_frame150.png','ros_integration.json','formal_integration.json','final_tests.json','gui_benchmark.json','preservation.json','native_integration.json','bag_topic_counts.json']
files=[]
for name in names:
    p=r/name
    if p.is_file():
        assert p.resolve().is_relative_to(r) and p.stat().st_size<5*1024**2
        files.append({'path':str(p),'name':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
print(json.dumps(files))
"""
try:
    audit.event('ssh.connect.requested',target_alias='isaac-new',channel='SFTP; ops CLI has no file-transfer verb');client.connect(**kwargs)
    response=remote_python(client,IDENTITY_SCRIPT,audit,'identity',20);assert response['exit_code']==0
    check_identity(json.loads(response['stdout']),target);audit.event('ssh.instance.verified',target_alias='isaac-new')
    audit.snapshot('evidence_manifest',script);response=remote_python(client,script,audit,'evidence-manifest',20);assert response['exit_code']==0
    manifest=json.loads(response['stdout']);sftp=client.open_sftp()
    for item in manifest:
        audit.event('artifact.download.requested',source=item['path'],destination=str(ROOT/'reports'/item['name']),sha256=item['sha256'])
        with sftp.open(item['path'],'rb') as f:data=f.read()
        assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
        dest=ROOT/'reports'/item['name'];dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and dest.read_bytes()!=data:
            backup=ROOT/'reports/history'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')/item['name'];backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(dest.read_bytes())
        dest.write_bytes(data);audit.event('artifact.download.verified',destination=str(dest),sha256=item['sha256'])
    sftp.close();audit.finish('succeeded');print(json.dumps({'files':[x['name'] for x in manifest],'audit_log':str(audit.path)},indent=2))
except BaseException as exc:
    audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
finally:client.close()
