"""Publish only the requested plan and six reviewed evidence files, with audit."""
import hashlib
import json
import os
import socket
import sys
import uuid
from pathlib import Path

import paramiko

sys.path.insert(0, 'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit, verify_file
from cloud_ops.security import Redactor, WindowsCredentials, private_directory
from cloud_ops.ssh import check_fingerprint, check_identity, remote_python

here = Path(__file__).resolve().parent
project = here.parent.parent
profile = project / 'migrations/20261010_dual_gpu/targets.json'
target = json.loads(profile.read_text())['targets']['isaac-dual']
remote_root = '/root/gpufree-data/semantic/scripts/260920SensorVisualizer'
names = ['docs/20261010_dual_gpu_v07_optimization_plan.md'] + [
    'research/20261010_dual_gpu/' + name for name in (
        'hardware_report.json', 'sdk_report.json', 'sdk_code_details.json',
        'device_path_report.json', 'findings_and_plan.json')]
files = []
for name in names:
    source = project / name
    data = source.read_bytes()
    if source.suffix == '.json':
        json.loads(data)
    files.append({'relative': name, 'bytes': len(data),
                  'sha256': hashlib.sha256(data).hexdigest(),
                  'temporary': str(Path(name).parent).replace('\\', '/') +
                  '/.codex-plan-' + uuid.uuid4().hex + '.tmp'})

secret = WindowsCredentials().read(target['credential_ref'])
redactor = Redactor([secret])
audit = Audit(private_directory(Path(os.environ['LOCALAPPDATA']) / 'CloudInstanceOps'),
              redactor, 'dual-gpu-optimization-plan-document',
              'Synchronize the requested plan and research evidence without changing runtime code',
              'audited-sftp-document-publish', hashlib.sha256(profile.read_bytes()).hexdigest())
client = paramiko.SSHClient()
transport = None
sftp = None
staged = []

def run_reviewed(script, label):
    redactor.reject_sensitive_text(script, 'Remote script')
    audit.snapshot(label, script)
    result = remote_python(client, script, audit, label, 30)
    if result['exit_code']:
        raise RuntimeError(label + ' failed')
    return json.loads(result['stdout'])

try:
    prior = Path(os.environ['LOCALAPPDATA']) / 'CloudInstanceOps/audit/20261010/20261010T074807Z_1037266724b2.jsonl'
    prior_records = [json.loads(line) for line in prior.read_text().splitlines()]
    assert [row['event'] for row in prior_records] == ['operation.started']
    audit.event('prior.local-operation.interrupted', operation_id=prior_records[0]['operation_id'],
                verified_local_pid=48328, reason='Local text scanning stalled before SSH dispatch',
                original_audit_preserved=True, original_completion='unknown',
                observed_events=['operation.started'])
    audit.event('sftp.publish.manifest', files=files, target_alias='isaac-dual')
    audit.event('ssh.connect.requested', target_alias='isaac-dual', host=target['host'],
                port=target['port'], username=target['username'], declared_intent='write')
    transport = paramiko.Transport(socket.create_connection((target['host'], target['port']), timeout=15))
    transport.start_client(timeout=15)
    check_fingerprint(transport.get_remote_server_key(), target['host_fingerprint'])
    audit.event('ssh.host_key.verified', fingerprint=target['host_fingerprint'])
    transport.auth_timeout = 15
    transport.auth_password(target['username'], secret)
    secret = None
    client._transport = transport
    audit.event('ssh.authenticated', target_alias='isaac-dual')
    identity = run_reviewed("import hashlib,json,os\nfrom pathlib import Path\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()}))\n", 'identity')
    check_identity(identity, target)
    audit.event('ssh.instance.verified', **identity)

    common = ('import hashlib,json,os\nfrom pathlib import Path\n'
              'root=Path(' + repr(remote_root) + ')\n'
              'items=' + repr(files) + '\n'
              'assert root.is_dir() and root.resolve()==root\n'
              'def safe(relative):\n'
              '    path=root/relative\n'
              '    assert path.resolve().is_relative_to(root) and path.resolve()==path\n'
              '    assert not path.is_symlink()\n'
              '    return path\n')
    preflight = run_reviewed(common +
              'missing=[]\n'
              'for item in items:\n'
              '    dst=safe(item["relative"]);tmp=safe(item["temporary"])\n'
              '    assert not tmp.exists()\n'
              '    if dst.exists():\n'
              '        assert dst.is_file() and hashlib.sha256(dst.read_bytes()).hexdigest()==item["sha256"],"Existing file differs"\n'
              '    else: missing.append(item["relative"])\n'
              'for item in items:\n'
              '    dst=safe(item["relative"]);dst.parent.mkdir(parents=True,exist_ok=True)\n'
              '    assert dst.parent.resolve()==dst.parent\n'
              'print(json.dumps({"missing":missing}))\n', 'preflight')
    sftp = paramiko.SFTPClient.from_transport(transport)
    sftp.get_channel().settimeout(30)
    for item in files:
        if item['relative'] not in preflight['missing']:
            continue
        data = (project / item['relative']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item['sha256']
        path = remote_root + '/' + item['temporary']
        audit.event('sftp.write.requested', path=path, bytes=len(data), sha256=item['sha256'])
        staged.append(path)
        with sftp.open(path, 'wx') as destination:
            destination.write(data)
            destination.flush()
        sftp.chmod(path, 0o644)
        audit.event('sftp.write.completed', path=path, bytes=len(data), sha256=item['sha256'])
    result = run_reviewed(common +
              'copied=[]\n'
              'for item in items:\n'
              '    dst=safe(item["relative"]);tmp=safe(item["temporary"])\n'
              '    if tmp.exists():\n'
              '        assert tmp.is_file() and hashlib.sha256(tmp.read_bytes()).hexdigest()==item["sha256"]\n'
              '    else: assert dst.is_file()\n'
              '    if dst.exists(): assert hashlib.sha256(dst.read_bytes()).hexdigest()==item["sha256"]\n'
              'for item in items:\n'
              '    dst=safe(item["relative"]);tmp=safe(item["temporary"])\n'
              '    if not dst.exists():\n'
              '        os.link(tmp,dst);copied.append(item["relative"])\n'
              '    if tmp.exists(): tmp.unlink()\n'
              '    assert hashlib.sha256(dst.read_bytes()).hexdigest()==item["sha256"]\n'
              'print(json.dumps({"passed":True,"files":len(items),"new_files":copied,"document":str(root/items[0]["relative"]),"document_sha256":items[0]["sha256"],"original_code_modified":False,"runtime_started":False}))\n', 'publish-and-verify')
    result['audit_operation_id'] = audit.id
    (here / 'plan_remote_deployment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    audit.event('document.deployment.verified', **result)
    audit.finish('succeeded')
    verification = verify_file(audit.path)
    assert verification['integrity'] == 'valid' and verification['completion'] == 'recorded'
    print(json.dumps(result, ensure_ascii=False))
except Exception as exc:
    if not audit.closed:
        audit.finish('failed', error_type=type(exc).__name__, error=redactor.text(str(exc)),
                     owned_temporary_paths=staged, remote_completion_requires_inspection=True)
    raise
finally:
    if sftp:
        sftp.close()
    client.close()
    if transport:
        transport.close()
