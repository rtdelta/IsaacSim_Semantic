"""Approved exact USD asset transfer through pinned project-scoped SSH audit."""
import hashlib,json,os,sys,warnings
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import remote_ops
sys.path.insert(0,str(remote_ops.OPS))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
 warnings.simplefilter('ignore');import paramiko
source=ROOT/'assets/native_rotation_localization/official/Example_Rotary.usda';data=source.read_bytes()
expected='0812faf5c310f40316d5a11ab0c6786e19e18ac12cea10edc2e7ee44fc56c8c6'
assert hashlib.sha256(data).hexdigest()==expected and len(data)==15137
assert b'@' not in data  # No external USD asset references in this exact text asset.
target=json.loads(remote_ops.PROFILE.read_text())['targets']['isaac-new'];redactor=Redactor();secret=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(secret)
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'native007-official-asset','User approved exact official USD asset; verified HTTPS download, no external references; SFTP project transfer','project-scoped-sftp',hashlib.sha256(remote_ops.PROFILE.read_bytes()).hexdigest())
class Pin(paramiko.MissingHostKeyPolicy):
 def missing_host_key(self,client,hostname,key):check_fingerprint(key,target['host_fingerprint']);audit.event('ssh.host_key.verified',target_alias='isaac-new')
client=paramiko.SSHClient();client.set_missing_host_key_policy(Pin())
try:
 client.connect(hostname=target['host'],port=target['port'],username=target['username'],password=secret,look_for_keys=False,allow_agent=False,timeout=20,banner_timeout=20,auth_timeout=20)
 identity=remote_python(client,IDENTITY_SCRIPT,audit,'identity',20);check_identity(json.loads(identity['stdout']),target)
 sftp=client.open_sftp();parent=str(remote_ops.REMOTE)
 import stat
 for name in ('assets','native_rotation_localization','official'):
  parent+='/'+name
  try:
   info=sftp.lstat(parent)
   if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):raise ValueError('Unsafe asset directory')
  except FileNotFoundError:sftp.mkdir(parent)
 dest=parent+'/Example_Rotary.usda'
 try:
  info=sftp.lstat(dest)
  with sftp.open(dest,'rb') as f:old=f.read()
  if old!=data:raise ValueError('Existing asset differs; refuse overwrite')
 except FileNotFoundError:
  with sftp.open(dest,'wx') as f:f.write(data)
 with sftp.open(dest,'rb') as f:assert hashlib.sha256(f.read()).hexdigest()==expected
 receipt={'path':dest,'sha256':expected,'bytes':len(data),'source':'NVIDIA official S3 Isaac 6.0 asset','upstream_hash_trust':'observed only','audit_log':str(audit.path),'external_asset_references':[]}
 audit.event('asset.transferred',**receipt);audit.finish('succeeded');(ROOT/'reports/native007_official_asset_transfer.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt))
except Exception as exc:audit.finish('failed',error=str(exc));raise
finally:client.close()
