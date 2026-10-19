import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
p=subprocess.run(['bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc006',str(R/'analyze_raw.py'),str(out)],capture_output=True,text=True,timeout=30)
print(p.stdout);print(p.stderr);raise SystemExit(p.returncode)
