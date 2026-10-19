"""Pull the inspected completed bag via pinned SFTP; verify every local file."""
import hashlib, inspect, json, os, shutil, sys, time, uuid, warnings
from pathlib import Path, PurePosixPath

SCRIPTS = Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
sys.path.insert(0, str(SCRIPTS))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor, WindowsCredentials, load_policy, private_directory
from cloud_ops.ssh import check_fingerprint, check_identity, remote_python, IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    import paramiko

here = Path(__file__).resolve().parent
envelope = json.loads((here/'download_source.json').read_text(encoding='utf-8-sig'))
assert envelope['status'] == 'succeeded' and envelope['result']['exit_code'] == 0
payload = json.loads(envelope['result']['stdout'])
source = PurePosixPath(payload['session'])
assert source.parent == PurePosixPath('/root/gpufree-data/semantic/output/sensor_visualizer')
output = Path('D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/output').resolve()
destination = output/source.name
if not destination.resolve().is_relative_to(output):
    raise ValueError('Destination outside output')
destination.mkdir(exist_ok=True, parents=True)
if shutil.disk_usage(output).free < sum(r['bytes'] for r in payload['files']) + 128*1024*1024:
    raise RuntimeError('Insufficient local disk space')
config = SCRIPTS/'config.json'
policy = load_policy(config)
target = policy['targets']['isaac-new']
state = private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps')
redactor = Redactor()
secret = WindowsCredentials().read(target['credential_ref'])
redactor.add_secret(secret)
audit = Audit(state, redactor, 'mcap-download-20260923',
              'Download user-requested completed unified MCAP to local output',
              'project_sftp_pull', hashlib.sha256(config.read_bytes()).hexdigest())

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

class Pinned(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        check_fingerprint(key, target['host_fingerprint'])
        audit.event('ssh.host_key.verified', fingerprint=target['host_fingerprint'])

client = paramiko.SSHClient()
client.set_missing_host_key_policy(Pinned())
manifest = []
try:
    audit.event('sftp.connect.requested', target_alias='isaac-new', direction='remote_to_local',
                script_sha256=digest(Path(__file__)), source=str(source), destination=str(destination),
                coverage='Explicit user-requested project data via SFTP; no external content installation')
    client.connect(target['host'], port=target['port'], username=target['username'], password=secret,
                   look_for_keys=False, allow_agent=False, timeout=15, banner_timeout=15, auth_timeout=15)
    identity = remote_python(client, IDENTITY_SCRIPT, audit, 'identity', 15)
    if identity['exit_code']:
        raise RuntimeError('Identity check failed')
    check_identity(json.loads(identity['stdout']), target)
    audit.event('ssh.instance.verified', target_alias='isaac-new')
    sftp = client.open_sftp()
    sftp.get_channel().settimeout(45)
    for row in payload['files']:
        rel = PurePosixPath(row['relative'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Invalid manifest path')
        src = str(source/rel)
        dst = destination.joinpath(*rel.parts)
        if not dst.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Destination escapes session folder')
        dst.parent.mkdir(exist_ok=True, parents=True)
        before = sftp.stat(src)
        expected = (row['bytes'], row['mtime_ns']//10**9)
        if (before.st_size, before.st_mtime) != expected:
            raise RuntimeError('Source changed since inspection')
        audit.event('sftp.file.requested', source=src, destination=str(dst), expected_sha256=row['sha256'])
        if dst.exists():
            if dst.stat().st_size != row['bytes'] or digest(dst) != row['sha256']:
                raise FileExistsError('Existing local file differs: '+str(dst))
            print(json.dumps({'file': str(rel), 'status': 'already_verified'}), flush=True)
        else:
            temp = dst.with_name(dst.name+'.'+uuid.uuid4().hex[:8]+'.part')
            last = [-1, time.monotonic()]
            def progress(done, total):
                percent = int(done*100/total) if total else 100
                now = time.monotonic()
                if percent//10 != last[0] or now-last[1] > 30:
                    last[:] = [percent//10, now]
                    print(json.dumps({'file': str(rel), 'percent': percent, 'received_mib': round(done/2**20, 1)}), flush=True)
            kwargs = {'callback': progress}
            if 'max_concurrent_prefetch_requests' in inspect.signature(sftp.get).parameters:
                kwargs['max_concurrent_prefetch_requests'] = 64
            sftp.get(src, str(temp), **kwargs)
            after = sftp.stat(src)
            if (after.st_size, after.st_mtime) != expected:
                raise RuntimeError('Source changed during transfer')
            if temp.stat().st_size != row['bytes'] or digest(temp) != row['sha256']:
                raise RuntimeError('Downloaded checksum mismatch')
            temp.rename(dst)
        item = {'source': src, 'destination': str(dst), 'bytes': row['bytes'], 'sha256': row['sha256']}
        manifest.append(item)
        audit.event('sftp.file.verified', **item)
    sftp.close()
    (destination/'download_manifest.json').write_text(json.dumps({'status': 'verified', 'files': manifest}, indent=2)+'\n', encoding='utf-8')
    audit.finish('succeeded', files=len(manifest), local_directory=str(destination))
    print(json.dumps({'status': 'verified', 'directory': str(destination), 'files': len(manifest),
                      'bytes': sum(r['bytes'] for r in manifest), 'audit_log': str(audit.path)}), flush=True)
except Exception as exc:
    audit.finish('failed', error=redactor.text(str(exc)))
    raise
finally:
    client.close()
