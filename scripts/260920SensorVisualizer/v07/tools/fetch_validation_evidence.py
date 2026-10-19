"""Audited SFTP of project-generated validation logs, excluding sensor payloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import paramiko
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python
root=Path(__file__).resolve().parents[1]
profile=root.parent/'migrations/20261010_dual_gpu/targets.json'
target=json.loads(profile.read_text())['targets']['isaac-dual']
parser=argparse.ArgumentParser();parser.add_argument('--run');args=parser.parse_args()
if args.run and not all(c.isdigit() or c=='_' for c in args.run):raise ValueError('Invalid run name')
secret=WindowsCredentials().read(target['credential_ref']);redactor=Redactor([secret])
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,
    'sensor-v07-implementation','Download project-generated validation evidence and verify observed hashes',
    'audited-sftp-evidence-read',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient();transport=None;sftp=None
try:
    audit.event('ssh.connect.requested',target_alias='isaac-dual',host=target['host'],port=target['port'],declared_intent='read')
    transport=paramiko.Transport(socket.create_connection((target['host'],target['port']),timeout=15));transport.start_client(timeout=15)
    check_fingerprint(transport.get_remote_server_key(),target['host_fingerprint'])
    audit.event('ssh.host_key.verified',fingerprint=target['host_fingerprint'])
    transport.auth_timeout=15;transport.auth_password(target['username'],secret);secret=None;client._transport=transport
    identity="import hashlib,json,os\nfrom pathlib import Path\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()}))\n"
    actual=remote_python(client,identity,audit,'identity',30);check_identity(json.loads(actual['stdout']),target)
    audit.event('ssh.instance.verified',target_alias='isaac-dual')
    script='''import json,hashlib
from pathlib import Path
project=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
base=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation')
requested=RUN_NAME
if requested:
    directory=base/requested
    result=json.loads((directory/'validation_result.json').read_text())
else:
    result=json.loads((project/'reports/native_validation_result.json').read_text())
    directory=Path(result['directory'])
assert directory.resolve().is_relative_to(base) and result['state'] in ('passed','failed')
rows=[];skipped=[]
for path in directory.rglob('*'):
    if not path.is_file() or path.is_symlink():continue
    relative=path.relative_to(directory)
    if any(part.startswith('bag_') for part in relative.parts) or path.suffix not in ('.json','.jsonl','.log'):continue
    if path.name in ('analysis.json','trace.json'):continue # regenerable analysis; raw logs remain immutable evidence
    if path.stat().st_size>64*1024*1024:skipped.append({'path':relative.as_posix(),'reason':'larger than 64 MiB; retained on cloud'});continue
    rows.append({'relative':relative.as_posix(),'remote':str(path),'bytes':path.stat().st_size,
                 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
assert sum(row['bytes'] for row in rows)<512*1024*1024
print(json.dumps({'run':directory.name,'result':result,'files':rows,'skipped':skipped}))
'''.replace('RUN_NAME',repr(args.run))
    audit.snapshot('evidence-selection',script)
    reply=remote_python(client,script,audit,'evidence-selection',60)
    if reply['exit_code']:raise RuntimeError(redactor.text(reply['stderr']))
    evidence=json.loads(reply['stdout']);destination=root/'reports/native_runs'/evidence['run'];destination.mkdir(parents=True,exist_ok=True)
    sftp=paramiko.SFTPClient.from_transport(transport);sftp.get_channel().settimeout(30)
    for row in evidence['files']:
        path=destination/row['relative'];path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise RuntimeError('Different local evidence exists: '+row['relative'])
        if not path.exists():sftp.get(row['remote'],str(path))
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('Evidence changed during transfer: '+row['relative'])
        audit.event('sftp.download.verified',remote_path=row['remote'],local_path=str(path),sha256=row['sha256'],bytes=row['bytes'])
    evidence['operation']=audit.id
    data=json.dumps(evidence,ensure_ascii=False,indent=2).encode('utf-8')
    previous=destination/'evidence_manifest.json'
    if previous.exists():
        old=json.loads(previous.read_text(encoding='utf-8'));old_id=old.get('operation','initial')
        archive=destination/('evidence_manifest.'+old_id+'.json')
        if not archive.exists():archive.write_bytes(previous.read_bytes())
    (destination/('evidence_manifest.'+audit.id+'.json')).write_bytes(data);previous.write_bytes(data)
    audit.event('operation.result',status='succeeded',files=len(evidence['files']),bytes=sum(r['bytes'] for r in evidence['files']),directory=str(destination))
    print(json.dumps({'passed':True,'run':evidence['run'],'state':evidence['result']['state'],'files':len(evidence['files']),
                      'bytes':sum(r['bytes'] for r in evidence['files']),'skipped':evidence['skipped'],'directory':str(destination),'operation':audit.id}))
except Exception as exc:
    audit.event('operation.result',status='failed',error=redactor.text(str(exc)));raise
finally:
    if sftp:sftp.close()
    if transport:transport.close()
