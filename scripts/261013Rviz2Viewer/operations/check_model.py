import json, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text())
r=subprocess.run(['/usr/bin/python3',str(root/'verify_model.py'),str(Path(latest['directory'])/'capture')],capture_output=True,text=True,timeout=30)
print(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-2000:]}))
