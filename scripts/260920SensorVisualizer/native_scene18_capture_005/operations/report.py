import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005')
base=Path(json.loads((root/'reports/latest.json').read_text())['directory'])
r=subprocess.run(['/usr/bin/python3',str(root/'tools/summarize.py'),str(base)],capture_output=True,text=True,timeout=90)
print(r.stdout);print(r.stderr);raise SystemExit(r.returncode)
