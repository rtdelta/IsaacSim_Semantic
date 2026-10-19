import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
p=subprocess.run(['/usr/bin/python3','-B','-m','unittest','discover','-s','tests'],cwd=root,capture_output=True,text=True,timeout=60)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout[-3000:],'stderr':p.stderr[-10000:]}))
