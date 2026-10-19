import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');directory=root/'reports/native_owner'
row=json.loads((directory/'acceptance_process.json').read_text())
print(json.dumps({'process':row,'status':json.loads((directory/'acceptance_status.json').read_text()) if (directory/'acceptance_status.json').exists() else {},
    'log_tail':Path(row['log']).read_text(errors='replace')[-5000:]}))
