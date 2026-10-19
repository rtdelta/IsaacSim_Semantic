"""Audited SFTP of curated lab evidence to its own project reports directory.

CLI has no transfer verb. Uses existing dependencies and credential references,
pins the host and validates identity, scopes paths, and verifies uploaded hashes.
"""
import hashlib,json,os,sys,warnings
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
 warnings.simplefilter('ignore');import paramiko
files=[]
sets=['followup_20261011_104521/trace_gated_stacks','followup_20261011_104521/trace_keepalive_stacks',
 'confirmation_20261011_110041/trace_graphics']
names=('analysis.json','public_api_frames.json','timeline.html','group_1_timeline.csv',
 'dependency_ledger.csv','resource_ledger.csv','native_memory_ledger.csv')
for folder in sets:
 for name in names:
  p=ROOT/'reports'/folder/name
  if p.is_file():files.append(p)
files.extend(ROOT/'reports'/name for name in ('confirmation_metrics.json','local_baseline_final_check.json',
 'quality_samples/quality_comparison.json','quality_samples/comparison_contact_sheet.png',
 'followup_20261011_104521_raw/interaction_keepalive/interaction_attribution.json',
 'confirmation_20261011_110041/interaction_gated/interaction_attribution.json'))
manifest=[{'path':p.relative_to(ROOT/'reports').as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files]
if sum(r['bytes'] for r in manifest)>25*1024**2:raise ValueError('Curated evidence unexpectedly large')
profile=ROOT.parent/'migrations/20261010_dual_gpu/targets.json';target=json.loads(profile.read_text())['targets']['isaac-new'];redactor=Redactor()
kwargs=dict(hostname=target['host'],port=target['port'],username=target['username'],look_for_keys=False,allow_agent=False,timeout=15,banner_timeout=15,auth_timeout=15)
if target['auth']=='windows-credential':
 value=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(value);kwargs['password']=value
elif target['auth']=='key':kwargs['key_filename']=target['identity_file']
else:raise ValueError('Unsupported credential reference')
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'SINGLE06_LAB',
 'Mirror curated reports into the same independent project for document links','project-report-sftp',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient()
class Pin(paramiko.MissingHostKeyPolicy):
 def missing_host_key(self,client,hostname,key):
  check_fingerprint(key,target['host_fingerprint']);audit.event('ssh.host_key.verified',target_alias='isaac-new')
client.set_missing_host_key_policy(Pin());remote=PurePosixPath('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab/reports')
try:
 audit.event('ssh.connect.requested',target_alias='isaac-new',channel='Audited SFTP; CLI transfer unsupported')
 client.connect(**kwargs);identity=remote_python(client,IDENTITY_SCRIPT,audit,'identity',15)
 if identity['exit_code']:raise RuntimeError('Identity query failed')
 check_identity(json.loads(identity['stdout']),target);audit.event('ssh.instance.verified',target_alias='isaac-new')
 script="""import hashlib,json,time
from pathlib import Path
root=Path(REMOTE);assert root.resolve()==root
manifest=MANIFEST;stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime())
for row in manifest:
 p=root/row['path'];assert p.resolve().is_relative_to(root)
 if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
  saved=root.parent/'deploy_history'/('reports_'+stamp)/row['path'];saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(p.read_bytes())
 p.parent.mkdir(parents=True,exist_ok=True)
print(json.dumps({'prepared':len(manifest)}))
""".replace('REMOTE',repr(str(remote))).replace('MANIFEST',repr(manifest))
 audit.snapshot('prepare_project_reports',script);r=remote_python(client,script,audit,'prepare_reports',30)
 if r['exit_code']:raise RuntimeError('Report path preparation failed')
 with client.open_sftp() as sftp:
  for p,row in zip(files,manifest):
   temp=str(remote/row['path'])+'.upload';sftp.put(str(p),temp);sftp.posix_rename(temp,str(remote/row['path']))
   audit.event('report.uploaded',path=row['path'],bytes=row['bytes'],sha256=row['sha256'])
 verify="""import hashlib,json
from pathlib import Path
root=Path(REMOTE);manifest=MANIFEST
assert all((root/r['path']).resolve().is_relative_to(root) and (root/r['path']).stat().st_size==r['bytes'] and hashlib.sha256((root/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in manifest)
(root/'curated_reports_manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'files_verified':len(manifest),'bytes':sum(r['bytes'] for r in manifest)}))
""".replace('REMOTE',repr(str(remote))).replace('MANIFEST',repr(manifest))
 audit.snapshot('verify_uploaded_reports',verify);r=remote_python(client,verify,audit,'verify_reports',30)
 if r['exit_code']:raise RuntimeError('Report verification failed')
 audit.finish('succeeded');print(json.dumps({'manifest':manifest,'audit_log':str(audit.path)},indent=2))
except BaseException as exc:
 audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
finally:client.close()
