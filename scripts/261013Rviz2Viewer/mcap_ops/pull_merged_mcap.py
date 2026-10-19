"""Download the verified merged project bag with resumable parallel SFTP ranges.

SFTP is outside the ops CLI; it uses the same pinned identity, credential
references and a serialized local audit. Only project-generated data is moved.
"""
import concurrent.futures
import datetime
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pull_mcap as connection
from cloud_ops.audit import verify_file

REMOTE = str(connection.REMOTE.parent / 'bag_merged')
DESTINATION = connection.DESTINATION / 'bag_merged'


def main():
    profile = ROOT.parent / '260920SensorVisualizer/migrations/20261010_dual_gpu/targets.json'
    target = json.loads(profile.read_text())['targets']['isaac-new']
    redactor = connection.Redactor()
    kwargs = dict(hostname=target['host'], port=target['port'], username=target['username'],
                  look_for_keys=False, allow_agent=False, timeout=20, banner_timeout=20, auth_timeout=20)
    if target['auth'] == 'windows-credential':
        secret = connection.WindowsCredentials().read(target['credential_ref'])
        redactor.add_secret(secret)
        kwargs['password'] = secret
    elif target['auth'] == 'key':
        kwargs['key_filename'] = target['identity_file']
    else:
        raise ValueError('Unsupported credential reference')
    audit = connection.Audit(connection.private_directory(Path(os.environ['LOCALAPPDATA']) / 'CloudInstanceOps'),
        redactor, '20261013-merge-single06-300', 'Continue authorized merged project MCAP download',
        'sftp-ranged-project-file-transfer', hashlib.sha256(profile.read_bytes()).hexdigest())
    audit.snapshot('transfer_script', Path(__file__).read_text(encoding='utf-8'))
    event_lock, progress_lock = threading.Lock(), threading.Lock()
    progress = {}
    channels = []
    client = connection.paramiko.SSHClient()

    def event(kind, **data):
        with event_lock:
            audit.event(kind, **data)

    class Pin(connection.paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            connection.check_fingerprint(key, target['host_fingerprint'])
            event('ssh.host_key.verified', target_alias='isaac-new')

    client.set_missing_host_key_policy(Pin())
    manifest_script = '''import hashlib,json
from pathlib import Path
root=Path(REMOTE)
assert root.resolve()==root and root.is_dir()
report=json.loads((root/'merge_verification.json').read_text())
assert report['verified'] and report['messages']==9006 and report['topics']==32 and report['groups']==300
assert report['exact_raw_message_comparison'] and report['source_files_unchanged']
files=[]
for item in report['files']:
    path=root/item['name'];st=path.stat()
    assert path.parent==root and not path.is_symlink()
    assert (st.st_size,st.st_mtime_ns)==(item['bytes'],item['mtime_ns'])
    files.append(item)
path=root/'merge_verification.json';st=path.stat()
files.append({'name':path.name,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
print(json.dumps({'remote':str(root),'files':files}))
'''.replace('REMOTE', repr(REMOTE))
    started = time.monotonic()
    try:
        event('ssh.connect.requested', target_alias='isaac-new', channel='SFTP with pinned SSH identity; ops CLI does not support SFTP')
        client.connect(**kwargs)
        identity = connection.remote_python(client, connection.IDENTITY_SCRIPT, audit, 'identity', 20)
        assert identity['exit_code'] == 0
        connection.check_identity(json.loads(identity['stdout']), target)
        event('ssh.instance.verified', target_alias='isaac-new')
        audit.snapshot('source_manifest_script', manifest_script)
        response = connection.remote_python(client, manifest_script, audit, 'merged-source-manifest', 30)
        assert response['exit_code'] == 0
        manifest = json.loads(response['stdout'])
        assert [x['name'] for x in manifest['files']] == ['bag_merged_0.mcap', 'metadata.yaml', 'merge_verification.json']
        DESTINATION.mkdir(exist_ok=True)
        assert DESTINATION.resolve().is_relative_to(connection.DESTINATION.resolve())
        manifest_path = DESTINATION / 'source_manifest.json'
        if manifest_path.exists():
            assert json.loads(manifest_path.read_text(encoding='utf-8'))['files'] == manifest['files'], 'Source changed; existing partials retained'
        manifest_path.write_text(json.dumps({**manifest, 'destination': str(DESTINATION), 'audit_log': str(audit.path)}, indent=2), encoding='utf-8')
        total = sum(item['bytes'] for item in manifest['files'])
        assert total < 6 * 1024 ** 3
        assert shutil.disk_usage(DESTINATION).free > 2 * total + 1024 ** 3
        parts = DESTINATION / '.transfer_parts'
        assert not parts.is_symlink()
        parts.mkdir(exist_ok=True)

        def download_range(item, start, stop, part, sftp):
            assert not part.is_symlink() and part.parent.resolve() == parts.resolve()
            offset = part.stat().st_size if part.exists() else 0
            assert offset <= stop - start
            key = part.name
            with progress_lock:
                progress[key] = offset
            sftp.get_channel().settimeout(60)
            source_path = REMOTE + '/' + item['name']
            st = sftp.stat(source_path)
            assert st.st_size == item['bytes'] and st.st_mtime == item['mtime_ns'] // 10 ** 9
            event('artifact.range.requested', source=source_path, local_part=str(part), start=start, stop=stop, resume_bytes=offset)
            with sftp.open(source_path, 'rb') as source, part.open('ab') as output:
                while start + offset < stop:
                    chunks = [(pos, min(32768, stop - pos)) for pos in range(start + offset, min(start + offset + 1024 ** 2, stop), 32768)]
                    for (_, size), data in zip(chunks, source.readv(chunks)):
                        assert len(data) == size, 'Short range read'
                        output.write(data)
                        offset += len(data)
                    with progress_lock:
                        progress[key] = offset
                output.flush()
                os.fsync(output.fileno())
            st = sftp.stat(source_path)
            assert st.st_size == item['bytes'] and st.st_mtime == item['mtime_ns'] // 10 ** 9
            event('artifact.range.completed', local_part=str(part), bytes=offset)
            return part

        jobs, results = [], []
        for item in manifest['files']:
            destination = DESTINATION / item['name']
            if destination.exists():
                assert destination.stat().st_size == item['bytes'] and connection.digest(destination) == item['sha256']
                with progress_lock:
                    progress[item['name']] = item['bytes']
                continue
            ranges = 4 if item['name'].endswith('.mcap') else 1
            width = (item['bytes'] + ranges - 1) // ranges
            for index in range(ranges):
                start, stop = index * width, min((index + 1) * width, item['bytes'])
                jobs.append((item, start, stop, parts / (item['name'] + '.range' + str(index))))
        for _ in jobs:
            channels.append(client.open_sftp())
        print(json.dumps({'phase': 'transfer_started', 'bytes': total, 'destination': str(DESTINATION)}), flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(download_range, *job, sftp) for job, sftp in zip(jobs, channels)]
            pending = set(futures)
            last_print = 0
            while pending:
                _, pending = concurrent.futures.wait(pending, timeout=5, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in futures:
                    if future.done() and future.exception():
                        client.close()
                        raise future.exception()
                now = time.monotonic()
                if now - last_print >= 10 or not pending:
                    with progress_lock:
                        done = sum(progress.values())
                    print(json.dumps({'phase': 'progress', 'bytes': done, 'total_bytes': total,
                                      'percent': round(100 * done / total, 2), 'elapsed_s': round(now - started, 1)}), flush=True)
                    last_print = now
            for future in futures:
                future.result()
        for item in manifest['files']:
            destination = DESTINATION / item['name']
            if not destination.exists():
                assembly = DESTINATION / (item['name'] + '.download.part')
                assert not assembly.exists(), 'Existing assembly retained for inspection'
                with assembly.open('xb') as output:
                    for job in jobs:
                        if job[0]['name'] == item['name']:
                            with job[3].open('rb') as source:
                                shutil.copyfileobj(source, output, 4 * 1024 ** 2)
                    output.flush()
                    os.fsync(output.fileno())
                assert assembly.stat().st_size == item['bytes'] and connection.digest(assembly) == item['sha256']
                assembly.rename(destination)
            event('artifact.download.verified', destination=str(destination), bytes=item['bytes'], sha256=item['sha256'])
            results.append({**item, 'matches_source': True})
        final_script = '''import hashlib,json
from pathlib import Path
root=Path(REMOTE);files=FILES
for item in files:
    path=root/item['name'];st=path.stat();digest=hashlib.sha256()
    assert (st.st_size,st.st_mtime_ns)==(item['bytes'],item['mtime_ns'])
    with path.open('rb') as stream:
        while block:=stream.read(4*1024**2):digest.update(block)
    assert digest.hexdigest()==item['sha256']
print(json.dumps({'remote_files_stable':True,'files':len(files)}))
'''.replace('REMOTE', repr(REMOTE)).replace('FILES', repr(manifest['files']))
        audit.snapshot('source_final_hash_script', final_script)
        response = connection.remote_python(client, final_script, audit, 'source-post-transfer-hashes', 60)
        assert response['exit_code'] == 0
        receipt = {**manifest, 'destination': str(DESTINATION), 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'verified': True, 'results': results, 'remote_files_stable': True, 'audit_log': str(audit.path), 'elapsed_s': time.monotonic() - started}
        (DESTINATION / 'transfer_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        for job in jobs:
            job[3].unlink()
        if not list(parts.iterdir()):
            parts.rmdir()
        audit.finish('succeeded', files=len(results), bytes=total)
        assert verify_file(audit.path)['integrity'] == 'valid'
        print(json.dumps({'phase': 'completed', 'verified': True, 'bytes': total, 'destination': str(DESTINATION), 'audit_log': str(audit.path)}), flush=True)
    except BaseException as exc:
        if not audit.closed:
            audit.finish('failed', error_type=type(exc).__name__, error=redactor.text(str(exc)))
        raise
    finally:
        for channel in channels:
            try:
                channel.close()
            except Exception:
                pass
        client.close()


if __name__ == '__main__':
    main()
