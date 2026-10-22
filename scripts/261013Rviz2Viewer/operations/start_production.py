"""Start the explicitly requested 300-group job, after smoke validation."""
import json, sys, runpy
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
previous=json.loads((root/'reports/latest_capture.json').read_text())
result=json.loads((Path(previous['directory'])/'capture/result.json').read_text())
assert previous['groups']==3 and result['validation']['passed'] and result['exit_code']==0
sys.argv=['start_capture.py','300']
runpy.run_path(str(root/'operations/start_capture.py'),run_name='__main__')
