import json
import subprocess
from pathlib import Path
script = Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer/mcap_ops_validation/merge_and_verify.py')
assert script.is_file() and not script.is_symlink()
response = subprocess.run(['bash', '-c', 'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B "$@"', 'mcap-verify', str(script), '--verify-existing'], capture_output=True, text=True, timeout=300)
print(json.dumps({'worker_exit_code': response.returncode, 'stdout': response.stdout, 'stderr': response.stderr}))
raise SystemExit(response.returncode)
