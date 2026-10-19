"""Download this requested delivery with audited, pinned SFTP and bounded reads.

Uses installed Paramiko 2.8 without upgrades. Remote files are never changed.
Partials may resume only under the same immutable inventory. Final disk bytes
are SHA-256 verified before the partial is renamed to the delivery filename.
"""
import hashlib
import json
import os
import shutil
import sys
import time
import warnings
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, 'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor, WindowsCredentials, private_directory
from cloud_ops.ssh import check_fingerprint, check_identity, remote_python, IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    import paramiko


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    inventory_path = ROOT/'reports/download_inventory.json'
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    destination = ROOT.parents[2]/'output/20261012_scene18_native_rt2_300_handoff'
    destination = destination.resolve()
    allowed = [PurePosixPath('/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643'),
               PurePosixPath('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/handoff')]
    for row in inventory['files']:
        remote = PurePosixPath(row['remote'])
        assert any(remote.is_relative_to(root) for root in allowed)
        assert (destination/row['relative']).resolve().is_relative_to(destination)
        assert row['bytes'] >= 0 and len(row['sha256']) == 64
    assert sum(row['bytes'] for row in inventory['files']) == inventory['total_bytes']
    if shutil.disk_usage(destination.parent).free < inventory['total_bytes'] + 2*1024**3:
        raise RuntimeError('Insufficient local free space')
    destination.mkdir(exist_ok=True)
    frozen_manifest = destination/'remote_inventory.json'
    if frozen_manifest.exists():
        assert json.loads(frozen_manifest.read_text(encoding='utf-8')) == inventory, 'Inventory changed since previous attempt'
    else:
        frozen_manifest.write_text(json.dumps(inventory, indent=2), encoding='utf-8')

    profile = ROOT.parent/'migrations/20261010_dual_gpu/targets.json'
    target = json.loads(profile.read_text())['targets']['isaac-new']
    redactor = Redactor()
    kwargs = dict(hostname=target['host'], port=target['port'], username=target['username'],
                  look_for_keys=False, allow_agent=False, timeout=15, banner_timeout=15, auth_timeout=15)
    if target['auth'] == 'windows-credential':
        secret = WindowsCredentials().read(target['credential_ref'])
        redactor.add_secret(secret)
        kwargs['password'] = secret
    elif target['auth'] == 'key':
        kwargs['key_filename'] = target['identity_file']
    else:
        raise ValueError('Unsupported registered authentication')
    audit = Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'), redactor,
                  'scene18-handoff-download-20261013', 'Download requested MCAP and full asset handoff to one local output directory',
                  'project-resumable-sftp', hashlib.sha256(profile.read_bytes()).hexdigest())
    client = paramiko.SSHClient()

    class Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            check_fingerprint(key, target['host_fingerprint'])
            audit.event('ssh.host_key.verified', target_alias='isaac-new')
    client.set_missing_host_key_policy(Pin())
    progress_path = destination/'download_progress.json'
    started = time.monotonic()
    progress = {'state': 'connecting', 'total_bytes': inventory['total_bytes'], 'verified_bytes': 0, 'verified_files': 0}
    last_print = 0.0
    last_write = 0.0

    def update(force=False):
        nonlocal last_print, last_write
        now = time.monotonic()
        if not force and now-last_write < 5:
            return
        progress['elapsed_s'] = round(now-started, 1)
        temporary = progress_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(progress, indent=2), encoding='utf-8')
        temporary.replace(progress_path)
        last_write = now
        if force or now-last_print > 30:
            print(json.dumps(progress), flush=True)
            last_print = now
    update(True)
    try:
        audit.event('ssh.connect.requested', target_alias='isaac-new', channel='Existing Paramiko SFTP; ops CLI has no file transfer verb')
        client.connect(**kwargs)
        identity = remote_python(client, IDENTITY_SCRIPT, audit, 'identity', 15)
        if identity['exit_code']:
            raise RuntimeError('Remote identity query failed')
        check_identity(json.loads(identity['stdout']), target)
        audit.event('ssh.instance.verified', target_alias='isaac-new')
        transport = client.get_transport()
        transport.set_keepalive(20)
        sftp = paramiko.SFTPClient.from_transport(transport, window_size=16*1024**2, max_packet_size=128*1024)
        sftp.get_channel().settimeout(60)
        verified = []
        for row in sorted(inventory['files'], key=lambda value: value['bytes']):
            local = destination/row['relative']
            local.parent.mkdir(parents=True, exist_ok=True)
            if sftp.stat(row['remote']).st_size != row['bytes']:
                raise RuntimeError('Remote size changed: '+row['relative'])
            if local.exists():
                if local.stat().st_size != row['bytes'] or digest_file(local) != row['sha256']:
                    raise FileExistsError('Existing local file differs: '+str(local))
            else:
                partial = local.with_suffix(local.suffix+'.part')
                offset = partial.stat().st_size if partial.exists() else 0
                assert offset <= row['bytes']
                progress.update(state='downloading', current_file=row['relative'], current_bytes=offset, current_total_bytes=row['bytes'])
                update(True)
                with sftp.open(row['remote'], 'rb') as remote, partial.open('ab') as output:
                    # 128 queued requests per 4 MiB batch, instead of unbounded
                    # prefetch of all 9 GB in this installed Paramiko version.
                    while offset < row['bytes']:
                        end = min(offset+4*1024**2, row['bytes'])
                        chunks = [(position, min(32768, end-position)) for position in range(offset, end, 32768)]
                        for block, (_, expected) in zip(remote.readv(chunks), chunks):
                            if len(block) != expected:
                                raise IOError('Unexpected truncated SFTP read')
                            output.write(block)
                            offset += len(block)
                        progress['current_bytes'] = offset
                        update()
                    output.flush()
                    os.fsync(output.fileno())
                progress['state'] = 'verifying_file'
                update(True)
                if partial.stat().st_size != row['bytes'] or digest_file(partial) != row['sha256']:
                    raise RuntimeError('SHA-256 mismatch; partial retained: '+row['relative'])
                partial.rename(local)
            progress['verified_bytes'] += row['bytes']
            progress['verified_files'] += 1
            verified.append(row)
            audit.event('artifact.transfer.verified', source=row['remote'], local_path=str(local),
                        bytes=row['bytes'], sha256=row['sha256'])
        sftp.close()
        (destination/'transfer_manifest.json').write_text(json.dumps({'verified': True, 'files': verified,
            'total_bytes': sum(r['bytes'] for r in verified), 'audit_log': str(audit.path)}, indent=2), encoding='utf-8')
        progress.update(state='completed', current_file=None, current_bytes=0, current_total_bytes=0)
        update(True)
        audit.finish('succeeded')
    except BaseException as exc:
        progress.update(state='failed', error=redactor.text(type(exc).__name__+': '+str(exc)))
        update(True)
        audit.finish('failed', error_type=type(exc).__name__, error=redactor.text(str(exc)))
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()
