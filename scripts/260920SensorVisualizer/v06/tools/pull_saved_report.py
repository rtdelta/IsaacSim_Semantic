"""Transfer a generated task report in bounded chunks and verify its full hash.

This does not re-run a report producer after a transport/JSON parsing failure.
Only v06 reports selected explicitly by the caller can be read.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import zlib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('name')
parser.add_argument('--task', default='v06-report-transfer')
args = parser.parse_args()
if Path(args.name).name != args.name or not args.name.endswith('.json'):
    raise ValueError('Select a JSON basename inside the task reports directory')
root = Path(__file__).resolve().parents[1]
helpers = root / 'reports' / 'transfer_helpers'
helpers.mkdir(parents=True, exist_ok=True)
remote = '/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/reports/' + args.name
ops = 'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py'
operations = []

def run(source, label):
    helper = helpers / (label + '.py')
    helper.write_text(source, encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', ops, 'exec', '--target', 'isaac-new',
         '--task', args.task, '--purpose', '读取本任务已生成的报告分片并校验完整性',
         '--script', str(helper), '--intent', 'read', '--timeout', '30'],
        capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stdout[-2000:] + result.stderr[-1000:])
    operation = json.loads(result.stdout)
    value = operation['result']
    if operation['status'] != 'succeeded' or value['exit_code'] or any(value['output_omitted']):
        raise RuntimeError('Report transfer failed: ' + operation['operation_id'])
    operations.append(operation['operation_id'])
    return json.loads(value['stdout'])

prefix = 'from pathlib import Path\nimport hashlib,json,zlib\np=Path(' + repr(remote) + ')\n'
source = prefix + "b=p.read_bytes()\nc=zlib.compress(b,9)\n"
source += "parts=[c[i:i+64].hex() for i in range(0,len(c),64)]\n"
source += "assert len(c)<80000,'Use smaller selected reports for transfer'\n"
source += "print(json.dumps({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'content':parts}))\n"
manifest = run(source, 'compressed_report')
if manifest['bytes'] > 4 * 1024 * 1024:
    raise ValueError('Unexpected task report size')
data = zlib.decompress(bytes.fromhex(''.join(manifest.pop('content'))))
if len(data) != manifest['bytes'] or hashlib.sha256(data).hexdigest() != manifest['sha256']:
    raise RuntimeError('Full report hash mismatch; no destination was replaced')
json.loads(data)
destination = root / 'reports' / args.name
temporary = destination.with_suffix('.json.transfer')
temporary.write_bytes(data)
temporary.replace(destination)
print(json.dumps({'saved':str(destination), **manifest, 'operation_ids':operations}))
