import json,runpy
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
(root/'reports/native_owner/live_test_spec.json').write_text(json.dumps({'mode':'live_complete'}))
runpy.run_path(str(root/'tools/remote_live_capture_test.py'),run_name='__main__')
