"""Read-only follow-up for a profiler mentioned in existing project records."""
from pathlib import Path
import json
import subprocess

paths = []
historical_path = Path('/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys')
if historical_path.is_file(): paths.append(str(historical_path))
for root in ('/opt/nvidia', '/usr/local/cuda', '/usr/local', '/usr/bin'):
    p = Path(root)
    if not p.is_dir(): continue
    for pattern in ('nsys', 'bin/nsys', '*nsight*/bin/nsys', '*nsight*/*/bin/nsys', 'nsight*/target-linux-x64/nsys'):
        paths.extend(str(x) for x in p.glob(pattern) if x.is_file())
result = {'intent': 'read only', 'nsys_candidates': sorted(set(paths))}
for name in result['nsys_candidates']:
    try:
        r = subprocess.run([name, '--version'], capture_output=True, text=True, timeout=5)
        result.setdefault('versions', []).append({'path': name, 'exit_code': r.returncode, 'stdout': r.stdout[:1000], 'stderr': r.stderr[:1000]})
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.setdefault('errors', []).append(str(exc))
print(json.dumps(result, indent=2))
