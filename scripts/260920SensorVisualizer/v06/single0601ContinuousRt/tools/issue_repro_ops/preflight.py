"""Read-only check for the independent issue reproduction; no environment dump."""
import json, shutil, subprocess
from pathlib import Path

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
processes = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        command = (p / 'cmdline').read_bytes()
        if b'/kit/kit' in command or (str(root).encode() in command and b'--worker' in command):
            processes.append({'pid': int(p.name), 'kit': b'/kit/kit' in command})
    except OSError:
        pass
print(json.dumps({'project_exists': root.is_dir(), 'free_bytes': shutil.disk_usage(root).free,
                  'competing_processes': processes,
                  'gpu': subprocess.run(['nvidia-smi', '--query-gpu=name,uuid,driver_version', '--format=csv,noheader'],
                                        capture_output=True, text=True, timeout=15).stdout.strip()}))
