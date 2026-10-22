import json
from pathlib import Path
path=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless/reports/continuous_capture_regression.json')
report=json.loads(path.read_text())
print(json.dumps({'state':report['state'],'error':report.get('error'),
    'cases':[{key:row.get(key) for key in ('label','state','groups','time_base','task_id','validation_exit_code')}
             for row in report['cases']]}))
