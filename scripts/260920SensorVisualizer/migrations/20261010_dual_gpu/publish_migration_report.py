"""Collect nonsecret verification reports and deploy this migration's handover."""
import hashlib,json,os,sys
from pathlib import Path
import paramiko
skill=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts');sys.path.insert(0,str(skill))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python
root=Path(__file__).resolve().parent;profile=root/'targets.json'
config=json.loads(profile.read_text());work='/root/gpufree-data/.migration_sensor_20261010_dual/'
creds=WindowsCredentials();secrets={alias:creds.read(config['targets'][alias]['credential_ref']) for alias in ('isaac-new','isaac-dual')}
redactor=Redactor(list(secrets.values()))
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,
            'dual-gpu-migration-handover','收集迁移验证并在新项目目录保存报告和启动说明','sftp-report-deploy',hashlib.sha256(profile.read_bytes()).hexdigest())
clients=[]
try:
    for alias in ('isaac-new','isaac-dual'):
        target=config['targets'][alias];t=paramiko.Transport((target['host'],target['port']));t.start_client(timeout=15)
        check_fingerprint(t.get_remote_server_key(),target['host_fingerprint']);t.auth_password(target['username'],secrets.pop(alias))
        client=paramiko.SSHClient();client._transport=t;clients.append(client)
        identity=remote_python(client,"import hashlib,json,os\nfrom pathlib import Path\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()}))\n",audit,alias+'-identity',30)
        check_identity(json.loads(identity['stdout']),target)
        sftp=paramiko.SFTPClient.from_transport(t)
        names=('source_key_cleanup.json','source_cleanup.json') if alias=='isaac-new' else ('runtime_validation.json','asset_layer_validation.json','target_cleanup.json')
        for name in names:
            with sftp.open(work+name,'rb') as f:data=f.read()
            json.loads(data);(root/name).write_bytes(data)
            audit.event('sftp.report.collected',target=alias,path=work+name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        if alias=='isaac-dual':
            path='/root/gpufree-data/semantic/scripts/260920SensorVisualizer/migrations/20261010_dual_gpu'
            built=''
            for component in path.split('/'):
                if not component:continue
                built+='/'+component
                try:sftp.stat(built)
                except FileNotFoundError:sftp.mkdir(built,mode=0o755)
            for name in ('README.md','migration_manifest.json','archive_metadata.json','migration_result.json','code_provenance.json',
                         'unit_validation.json','runtime_validation.json','asset_layer_validation.json','source_key_cleanup.json','source_cleanup.json','target_cleanup.json'):
                data=(root/name).read_bytes();dest=path+'/'+name
                try:
                    with sftp.open(dest,'rb') as f:old=f.read()
                    if old!=data:raise RuntimeError('Existing migration report differs: '+name)
                except FileNotFoundError:
                    with sftp.open(dest,'wb') as f:f.write(data)
                with sftp.open(dest,'rb') as f:assert f.read()==data
                audit.event('sftp.report.deployed',target=alias,path=dest,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        sftp.close()
    audit.finish('succeeded');print(json.dumps({'passed':True,'local_report':str(root/'README.md'),'remote_report':path+'/README.md','reports':11}))
except Exception as exc:
    audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
finally:
    for client in clients:client.close()
