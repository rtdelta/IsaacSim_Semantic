"""Audited SFTP delivery of this project's source/docs; no downloads or credentials in files."""
import hashlib,json,os,sys,warnings,uuid,datetime
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
 warnings.simplefilter('ignore');import paramiko
remote=PurePosixPath('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
profile=ROOT.parent/'migrations/20261010_dual_gpu/targets.json';target=json.loads(profile.read_text())['targets']['isaac-new'];redactor=Redactor()
kwargs=dict(hostname=target['host'],port=target['port'],username=target['username'],look_for_keys=False,allow_agent=False,timeout=20,banner_timeout=20,auth_timeout=20)
if target['auth']=='windows-credential':
 value=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(value);kwargs['password']=value
elif target['auth']=='key':kwargs['key_filename']=target['identity_file']
else:raise ValueError('Unsupported credential reference')
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'scene18-lidar-equivalence-006','Finalize self generated project source, report and figures','project-delivery-sftp',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient()
class Pin(paramiko.MissingHostKeyPolicy):
 def missing_host_key(self,client,hostname,key):check_fingerprint(key,target['host_fingerprint']);audit.event('ssh.host_key.verified',target_alias='isaac-new')
client.set_missing_host_key_policy(Pin())
manifest={}
for p in ROOT.rglob('*'):
 rel=p.relative_to(ROOT)
 if not p.is_file() or any(x in rel.parts for x in ('reports','results','operations','__pycache__','deploy_history')) or p.suffix not in ('.py','.json','.md','.patch','.png','.kit','.zip'):continue
 assert p.stat().st_size<10*1024**2
 manifest[rel.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
assert sum((ROOT/r).stat().st_size for r in manifest)<30*1024**2
script="""import hashlib,json
from pathlib import Path
r=Path(ROOT);paths=PATHS;result={}
assert r.resolve()==r
for s in paths:
 p=r/s
 assert p.resolve().is_relative_to(r)
 result[s]=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
print(json.dumps(result))
""".replace('ROOT',repr(str(remote))).replace('PATHS',repr(list(manifest)))
try:
 audit.event('ssh.connect.requested',target_alias='isaac-new',channel='SFTP; ops CLI has no file-transfer verb');client.connect(**kwargs)
 response=remote_python(client,IDENTITY_SCRIPT,audit,'identity',20);assert response['exit_code']==0
 check_identity(json.loads(response['stdout']),target);audit.event('ssh.instance.verified',target_alias='isaac-new')
 audit.snapshot('manifest_query',script);response=remote_python(client,script,audit,'delivery-before',30);assert response['exit_code']==0
 before=json.loads(response['stdout']);sftp=client.open_sftp();changed=[];stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')
 def mkdirs(p):
  assert p.is_relative_to(remote)
  if p==remote:return
  try:sftp.stat(str(p))
  except FileNotFoundError:mkdirs(p.parent);sftp.mkdir(str(p))
 for rel,sha in manifest.items():
  if before[rel]==sha:continue
  p=remote/rel;mkdirs(p.parent)
  if before[rel] is not None:
   with sftp.open(str(p),'rb') as f:old=f.read()
   assert hashlib.sha256(old).hexdigest()==before[rel]
   backup=remote/'deploy_history'/stamp/rel;mkdirs(backup.parent)
   with sftp.open(str(backup),'wx') as f:f.write(old)
  part=p.with_name(p.name+'.'+uuid.uuid4().hex+'.part')
  audit.event('artifact.upload.requested',destination=str(p),sha256=sha)
  sftp.put(str(ROOT/rel),str(part))
  with sftp.open(str(part),'rb') as f:assert hashlib.sha256(f.read()).hexdigest()==sha
  sftp.posix_rename(str(part),str(p));changed.append(rel)
  audit.event('artifact.upload.verified',destination=str(p),sha256=sha)
 sftp.close();response=remote_python(client,script,audit,'delivery-after',30);assert response['exit_code']==0
 after=json.loads(response['stdout']);assert after==manifest
 receipt={'verified_files':len(manifest),'changed':changed,'remote':str(remote),'manifest':manifest,'audit_log':str(audit.path)}
 (ROOT/'reports/final_delivery.json').write_text(json.dumps(receipt,indent=2));audit.finish('succeeded');print(json.dumps({'verified_files':len(manifest),'changed':changed,'audit_log':str(audit.path)},indent=2))
except BaseException as exc:
 audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
finally:client.close()
