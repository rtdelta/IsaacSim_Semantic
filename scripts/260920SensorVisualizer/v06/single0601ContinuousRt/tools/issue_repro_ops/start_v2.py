import subprocess
from pathlib import Path
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
result = subprocess.run(['/usr/bin/python3', '-B', str(root/'tools/issue_repro_ops/run_suite.py'),
                         '--id', 'minimal_20261016_v2'], cwd=root, capture_output=True, text=True, timeout=20)
print(result.stdout)
if result.returncode:
    print(result.stderr[-3000:])
    raise SystemExit(result.returncode)
