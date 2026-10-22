"""Retrieve the inspected recording through pinned, audited SFTP."""
import hashlib
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import sys
import uuid
import warnings

SCRIPTS=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
sys.path.insert(0,str(SCRIPTS))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,load_policy,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore');import paramiko

HERE=Path(__file__).resolve().parent
envelope=json.loads((HERE/'latest_bag.json').read_text(encoding='utf-8-sig'))
assert envelope['status']=='succeeded'
payload=json.loads(envelope['result']['stdout'])
assert payload['inspection_exit']==0
source=PurePosixPath(payload['session'])
remote_root=PurePosixPath('/root/gpufree-data/semantic/output/sensor_visualizer')
assert source.parent==remote_root
output=Path('D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/output').resolve()
destination=output/source.name
destination.mkdir(parents=True,exist_ok=True)
config=SCRIPTS/'config.json';policy=load_policy(config);target=policy['targets']['isaac-new']
state=private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps')
redactor=Redactor();secret=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(secret)
audit=Audit(state,redactor,'mcap-download-20260922','Download user-requested completed recording to local output',
            'project_sftp_pull',hashlib.sha256(config.read_bytes()).hexdigest())

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

class Pinned(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self,client,hostname,key):
        check_fingerprint(key,target['host_fingerprint'])
        audit.event('ssh.host_key.verified',fingerprint=target['host_fingerprint'])

client=paramiko.SSHClient();client.set_missing_host_key_policy(Pinned())
manifest=[]
try:
    audit.event('sftp.connect.requested',target_alias='isaac-new',direction='remote_to_local',
                coverage='explicit recording files; self-generated data, not external content download')
    client.connect(target['host'],port=target['port'],username=target['username'],password=secret,
                   look_for_keys=False,allow_agent=False,timeout=15,banner_timeout=15,auth_timeout=15)
    identity=remote_python(client,IDENTITY_SCRIPT,audit,'identity',15)
    if identity['exit_code']:raise RuntimeError('Identity check failed')
    check_identity(json.loads(identity['stdout']),target)
    audit.event('ssh.instance.verified',target_alias='isaac-new')
    sftp=client.open_sftp();sftp.get_channel().settimeout(45)
    for row in payload['files']:
        rel=PurePosixPath(row['relative'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unexpected relative path')
        src=str(source/rel);dst=destination.joinpath(*rel.parts)
        if not dst.resolve().is_relative_to(output):raise ValueError('Outside local output')
        dst.parent.mkdir(parents=True,exist_ok=True)
        stat=sftp.stat(src)
        if stat.st_size!=row['bytes'] or stat.st_mtime!=row['mtime_ns']//10**9:
            raise RuntimeError('Remote file changed since inspection')
        audit.event('sftp.file.requested',source=src,destination=str(dst),expected_sha256=row['sha256'])
        if dst.exists():
            if digest(dst)!=row['sha256']:raise FileExistsError('Existing local file differs: '+str(dst))
            print(json.dumps(dict(file=rel.as_posix(),status='already_verified')),flush=True)
        else:
            temp=dst.with_name(dst.name+'.'+uuid.uuid4().hex[:8]+'.part')
            last=[-1]
            def progress(done,total):
                percent=int(done*100/total) if total else 100
                bucket=percent//10
                if bucket!=last[0]:
                    last[0]=bucket
                    print(json.dumps(dict(file=rel.as_posix(),percent=percent,received_mib=round(done/2**20,1))),flush=True)
            kwargs=dict(callback=progress)
            if 'max_concurrent_prefetch_requests' in inspect.signature(sftp.get).parameters:
                kwargs['max_concurrent_prefetch_requests']=64
            sftp.get(src,str(temp),**kwargs)
            if digest(temp)!=row['sha256']:raise ValueError('Transfer checksum mismatch: '+src)
            temp.replace(dst)
        item=dict(source=src,destination=str(dst),bytes=dst.stat().st_size,sha256=row['sha256'])
        manifest.append(item);audit.event('sftp.file.verified',**item)
    sftp.close()
    details=json.loads(payload['stdout'])
    (destination/'bag_inspection.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (destination/'download_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    audit.finish('succeeded',files=len(manifest),local_directory=str(destination))
    print(json.dumps(dict(status='verified',directory=str(destination),files=len(manifest),audit_log=str(audit.path))),flush=True)
except Exception as exc:
    audit.finish('failed',error=str(exc));raise
finally:
    client.close()
