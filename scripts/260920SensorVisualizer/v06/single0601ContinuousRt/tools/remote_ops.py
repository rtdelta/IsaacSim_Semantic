"""Project-scoped pinned SSH, SFTP and local audit. Never takes secret values."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import warnings

PROJECT = Path(__file__).resolve().parents[1]
PROFILE = PROJECT.parents[1] / 'migrations/20261010_dual_gpu/targets.json'
OPS = Path.home() / '.codex/skills/cloud-instance-ops/scripts'
REMOTE = PurePosixPath('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['exec', 'deploy', 'pull','pull-tree','publish-report'])
    p.add_argument('--script')
    p.add_argument('--intent', default='read', choices=['read', 'write', 'diagnostic'])
    p.add_argument('--timeout', type=int, default=40)
    p.add_argument('--purpose', required=True)
    p.add_argument('--name', default='remote_result')
    p.add_argument('--remote-path')
    p.add_argument('--include-prefix',action='append',help='Deploy only project-relative prefixes; repeatable, never absolute or parent traversal')
    p.add_argument('--report-name',choices=['continuous_recovery_result.json','project_acceptance_20261014.json'])
    args = p.parse_args()
    if args.include_prefix:
        if args.action!='deploy':raise ValueError('include-prefix is only supported for deploy')
        for prefix in args.include_prefix:
            rel=PurePosixPath(prefix)
            if not prefix or rel.is_absolute() or '..' in rel.parts or '\\' in prefix or ':' in prefix:raise ValueError('Unsafe deployment prefix')
    (PROJECT / 'reports').mkdir(exist_ok=True)
    if args.action == 'exec':
        cmd = [sys.executable, '-X', 'utf8', str(OPS / 'ops.py'), '--config', str(PROFILE),
               'exec', '--target', 'isaac-new', '--task', '20261013-continuous-rt',
               '--purpose', args.purpose, '--script', str(Path(args.script).resolve()),
               '--intent', args.intent, '--timeout', str(args.timeout)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if not result.stdout.strip():
            raise RuntimeError('SSH wrapper failed: ' + result.stderr[:2000])
        response = json.loads(result.stdout)
        (PROJECT / 'reports' / (args.name + '_response.json')).write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding='utf-8')
        data = response.get('result', {})
        if response.get('status') == 'succeeded' and data.get('exit_code') == 0:
            raw = data.get('stdout', '')
            (PROJECT / 'reports' / (args.name + '.json')).write_text(raw, encoding='utf-8')
            print(raw)
        else:
            print(json.dumps(response, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        return
    sys.path.insert(0, str(OPS))
    from cloud_ops.audit import Audit
    from cloud_ops.security import Redactor, WindowsCredentials, private_directory
    from cloud_ops.ssh import check_fingerprint, check_identity, remote_python, IDENTITY_SCRIPT
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        import paramiko
    target = json.loads(PROFILE.read_text())['targets']['isaac-new']
    redactor = Redactor()
    secret = WindowsCredentials().read(target['credential_ref'])
    redactor.add_secret(secret)
    audit = Audit(private_directory(Path(os.environ['LOCALAPPDATA']) / 'CloudInstanceOps'),
                  redactor, '20261013-continuous-rt', args.purpose,
                  'project-scoped-sftp', hashlib.sha256(PROFILE.read_bytes()).hexdigest())
    class Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            check_fingerprint(key, target['host_fingerprint'])
            audit.event('ssh.host_key.verified', target_alias='isaac-new')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(Pin())
    try:
        audit.event('ssh.connect.requested', target_alias='isaac-new', channel='SFTP; outside ops CLI transfer coverage')
        client.connect(hostname=target['host'], port=target['port'], username=target['username'],
                       password=secret, look_for_keys=False, allow_agent=False,
                       timeout=20, banner_timeout=20, auth_timeout=20)
        identity = remote_python(client, IDENTITY_SCRIPT, audit, 'identity', 20)
        check_identity(json.loads(identity['stdout']), target)
        audit.event('ssh.instance.verified', target_alias='isaac-new')
        sftp = client.open_sftp()
        if args.action=='publish-report':
            if args.report_name is None:raise ValueError('Select one supported generated report')
            local=PROJECT/'reports'/args.report_name
            data=local.read_bytes()
            if len(data)>2*1024*1024 or json.loads(data).get('schema_version')!=1:
                raise ValueError('Generated report is outside the declared JSON/byte bounds')
            parent=REMOTE/'reports'
            attrs=sftp.lstat(str(parent))
            if stat.S_ISLNK(attrs.st_mode) or not stat.S_ISDIR(attrs.st_mode):
                raise ValueError('Generated report destination must be a real project directory')
            dst=parent/args.report_name
            backup=None
            try:
                attrs=sftp.lstat(str(dst))
                if not stat.S_ISREG(attrs.st_mode) or attrs.st_size>2*1024*1024:
                    raise ValueError('Refuse unexpected generated report overwrite')
                with sftp.open(str(dst),'rb') as stream:previous=stream.read()
                backup_dir=REMOTE/'.deploy_backups'/audit.id
                for folder in (REMOTE/'.deploy_backups',backup_dir):
                    try:
                        info=sftp.lstat(str(folder))
                        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):raise ValueError('Backup must be a real directory')
                    except FileNotFoundError:sftp.mkdir(str(folder))
                backup=backup_dir/args.report_name
                with sftp.open(str(backup),'wb') as stream:stream.write(previous)
            except FileNotFoundError:pass
            temporary=parent/('.'+args.report_name+'.'+audit.id+'.upload')
            with sftp.open(str(temporary),'wx') as stream:stream.write(data)
            digest=hashlib.sha256(data).hexdigest()
            with sftp.open(str(temporary),'rb') as stream:actual=hashlib.sha256(stream.read()).hexdigest()
            if actual!=digest:raise ValueError('Generated report transfer hash mismatch')
            sftp.posix_rename(str(temporary),str(dst))
            audit.event('project.generated_report.published',path=str(dst),sha256=digest,size_bytes=len(data),backup=str(backup) if backup else None)
            print(json.dumps({'report':args.report_name,'bytes':len(data),'sha256':digest,'audit_log':str(audit.path)}))
        elif args.action in ('pull','pull-tree'):
            rel = PurePosixPath(args.remote_path)
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Pull path must stay inside this project')
            remote = REMOTE / rel
            local = PROJECT / 'reports' / 'remote' / Path(str(rel))
            paths=[]
            def inventory(path,relative):
                info=sftp.lstat(str(path))
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError('Evidence transfer refuses symbolic links')
                if stat.S_ISDIR(info.st_mode):
                    for item in sftp.listdir_attr(str(path)):
                        if item.filename in ('.','..') or '/' in item.filename or '\\' in item.filename:
                            raise ValueError('Invalid SFTP entry')
                        inventory(path/item.filename,relative/item.filename)
                elif stat.S_ISREG(info.st_mode):
                    paths.append((path,relative,info.st_size))
                else:
                    raise ValueError('Evidence transfer accepts only ordinary files/directories')
            if args.action=='pull':
                paths=[(remote,PurePosixPath('.'),sftp.lstat(str(remote)).st_size)]
            else:
                inventory(remote,PurePosixPath('.'))
                if sum(n for _,_,n in paths)>256*1024*1024:
                    raise ValueError('Evidence transfer exceeds 256 MiB')
            for remote_path,relative,size in paths:
                destination=local if args.action=='pull' else local/Path(str(relative))
                destination.parent.mkdir(parents=True,exist_ok=True)
                sftp.get(str(remote_path),str(destination))
                h=hashlib.sha256()
                with destination.open('rb') as file:
                    for block in iter(lambda:file.read(1024*1024),b''):h.update(block)
                with sftp.open(str(remote_path),'rb') as file:
                    remote_hash=hashlib.sha256()
                    for block in iter(lambda:file.read(1024*1024),b''):remote_hash.update(block)
                if destination.stat().st_size!=size or h.hexdigest()!=remote_hash.hexdigest():
                    raise ValueError('Evidence transfer hash/size mismatch')
                audit.event('project.file.pulled',path=str(destination),sha256=h.hexdigest(),size_bytes=size)
            print(json.dumps({'directory':str(local),'verified_files':len(paths),'bytes':sum(n for _,_,n in paths)}))
        else:
            def mkdir(path):
                try:
                    attrs = sftp.lstat(str(path))
                    if stat.S_ISLNK(attrs.st_mode) or not stat.S_ISDIR(attrs.st_mode):
                        raise ValueError('Remote target is not a real directory: ' + str(path))
                except FileNotFoundError:
                    mkdir(path.parent)
                    sftp.mkdir(str(path))
            mkdir(REMOTE)
            changed = []
            for f in sorted(PROJECT.rglob('*')):
                rel = f.relative_to(PROJECT)
                if args.include_prefix and not any(rel.as_posix()==prefix.rstrip('/') or rel.as_posix().startswith(prefix.rstrip('/')+'/') for prefix in args.include_prefix):
                    continue
                if not f.is_file() or any(x in rel.parts for x in ('reports', '__pycache__', '.pytest_cache', '.deploy_backups')):
                    continue
                if f.suffix not in ('.py', '.json', '.md', '.sh', '.kit', '.png', '.bin', '.jsonl'):
                    continue
                dst = REMOTE / PurePosixPath(rel.as_posix())
                mkdir(dst.parent)
                data = f.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                try:
                    attrs = sftp.lstat(str(dst))
                    if stat.S_ISLNK(attrs.st_mode):
                        raise ValueError('Refuse remote symbolic-link overwrite')
                    previous = sftp.open(str(dst), 'rb').read()
                    if hashlib.sha256(previous).hexdigest() == digest:
                        continue
                    backup = REMOTE / '.deploy_backups' / audit.id / PurePosixPath(rel.as_posix())
                    mkdir(backup.parent)
                    with sftp.open(str(backup), 'wb') as out:
                        out.write(previous)
                except FileNotFoundError:
                    pass
                with sftp.open(str(dst), 'wb') as out:
                    out.write(data)
                actual = hashlib.sha256(sftp.open(str(dst), 'rb').read()).hexdigest()
                if actual != digest:
                    raise RuntimeError('Transfer hash mismatch: ' + rel.as_posix())
                changed.append({'path': rel.as_posix(), 'size_bytes': len(data), 'sha256': digest})
            audit.event('project.deployed', files=changed, remote_root=str(REMOTE))
            receipt = {'verified_files': len(changed), 'files': changed, 'audit_log': str(audit.path)}
            (PROJECT / 'reports' / 'deployment.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print(json.dumps({'verified_files': len(changed), 'audit_log': str(audit.path)}))
        sftp.close()
        audit.finish('succeeded')
    except Exception as exc:
        audit.finish('failed', error=str(exc))
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()
