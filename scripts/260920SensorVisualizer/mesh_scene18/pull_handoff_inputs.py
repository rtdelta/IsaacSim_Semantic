"""Read self-generated lab evidence over audited SFTP (CLI has no file-transfer verb).

Uses existing credential references and fingerprint/instance validation. No cloud
file writes. Hash consistency is transfer evidence, not software trust assurance.
"""
import argparse,hashlib,json,os,sys,warnings
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore');import paramiko

p=argparse.ArgumentParser();p.add_argument('remote_directory');p.add_argument('--destination',required=True);p.add_argument('--exclude-name',action='append',default=[]);p.add_argument('--include-path',action='append',default=[]);a=p.parse_args()
remote=PurePosixPath(a.remote_directory)
if not any(remote.is_relative_to(PurePosixPath(r)) for r in ('/root/gpufree-data/semantic/output/mesh_scene18','/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18','/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_Mesh_Contract','/root/gpufree-data/IsaacSim_Asset/combine_stage','/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02')):
    raise ValueError('Only native baseline output is allowed')
profile=ROOT.parent/'migrations/20261010_dual_gpu/targets.json'
target=json.loads(profile.read_text())['targets']['isaac-new'];redactor=Redactor()
kwargs=dict(hostname=target['host'],port=target['port'],username=target['username'],
            look_for_keys=False,allow_agent=False,timeout=15,banner_timeout=15,auth_timeout=15)
if target['auth']=='windows-credential':
    value=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(value);kwargs['password']=value
elif target['auth']=='key':kwargs['key_filename']=target['identity_file']
else:raise ValueError('Unsupported credential reference')
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'scene18-mesh-implementation-20261012',
            'Transfer canonical five-part mesh source for exact reconstruction handoff',
            'project-evidence-sftp',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient()
class Pin(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self,client,hostname,key):
        check_fingerprint(key,target['host_fingerprint']);audit.event('ssh.host_key.verified',target_alias='isaac-new')
client.set_missing_host_key_policy(Pin())
destination=Path(a.destination).resolve();destination.mkdir(parents=True,exist_ok=True)
try:
    audit.event('ssh.connect.requested',target_alias='isaac-new',channel='SFTP through existing Paramiko; CLI transfer unsupported')
    client.connect(**kwargs)
    identity=remote_python(client,IDENTITY_SCRIPT,audit,'identity',15)
    if identity['exit_code']:raise RuntimeError('Identity query failed')
    check_identity(json.loads(identity['stdout']),target);audit.event('ssh.instance.verified',target_alias='isaac-new')
    script="""import hashlib,json
from pathlib import Path
root=Path(REMOTE)
assert root.resolve()==root
allowed={'.json','.jsonl','.csv','.log','.sqlite','.nsys-rep','.jpg','.png','.md','.html','.usda','.usdc'}
excluded=EXCLUDED
included=INCLUDED
rows=[]
for p in sorted(root.rglob('*')):
 if not p.is_file() or p.suffix not in allowed or any(x in p.relative_to(root).parts for x in ('input_trajectory','bag_unified')):continue
 if included and p.relative_to(root).as_posix() not in included:continue
 if p.name in excluded:continue
 if any(x.startswith('round_') for x in root.parts) and p.name=='progress.json':continue
 assert p.resolve().is_relative_to(root)
 if p.stat().st_size>512*1024**2:raise RuntimeError('Large artifact requires explicit selection')
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 rows.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
assert sum(r['bytes'] for r in rows)<2*1024**3
print(json.dumps(rows))
""".replace('REMOTE',repr(str(remote))).replace('EXCLUDED',repr(a.exclude_name)).replace('INCLUDED',repr(a.include_path))
    audit.event('artifact.transfer.scope',excluded_names=a.exclude_name,included_paths=a.include_path)
    audit.snapshot('manifest_query',script)
    response=remote_python(client,script,audit,'artifact-manifest',60)
    if response['exit_code'] or any(response['output_omitted']):raise RuntimeError('Manifest query failed')
    manifest=json.loads(response['stdout']);sftp=client.open_sftp()
    for row in manifest:
        dest=destination/row['path']
        if not dest.resolve().is_relative_to(destination):raise ValueError('Unexpected artifact path')
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest()==row['sha256']:continue
        if dest.exists():raise FileExistsError('Existing differing evidence: '+str(dest))
        partial=dest.with_suffix(dest.suffix+'.part')
        if partial.exists():raise FileExistsError(str(partial))
        sftp.get(str(remote/row['path']),str(partial))
        if partial.stat().st_size!=row['bytes'] or hashlib.sha256(partial.read_bytes()).hexdigest()!=row['sha256']:
            raise RuntimeError('Transfer mismatch; partial retained')
        partial.rename(dest);audit.event('artifact.transfer.verified',source=str(remote/row['path']),
            local_path=str(dest),bytes=row['bytes'],sha256=row['sha256'])
    sftp.close();(destination/'transfer_manifest.json').write_text(json.dumps(manifest,indent=2))
    audit.finish('succeeded');print(json.dumps({'files':len(manifest),'bytes':sum(r['bytes'] for r in manifest),
        'destination':str(destination),'audit_log':str(audit.path)},indent=2))
except BaseException as exc:
    audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
finally:client.close()
