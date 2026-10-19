import json,runpy
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
runpy.run_path(str(root/'tools/remote_stop_owner_test.py'),run_name='__main__')
(root/'reports/native_owner/owner_test_options.json').write_text(json.dumps({'gui':True}))
runpy.run_path(str(root/'tools/remote_start_owner_test.py'),run_name='__main__')
