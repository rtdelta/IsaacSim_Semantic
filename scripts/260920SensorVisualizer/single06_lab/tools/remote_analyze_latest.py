"""Analyze completed evidence using existing stdlib; prints concise useful fields."""
import json,sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab');sys.path.insert(0,str(root))
from lab.analysis import analyze
record=json.loads((root/'reports/latest_execution.json').read_text());directory=Path(record['directory'])
r=analyze(directory)
print(json.dumps({'directory':str(directory),'host_stages':{k:v for k,v in r['host_stages'].items() if k in
 ('lab.SceneStepper.initialize','lab.SceneStepper.capture','lab.SceneStepper.close','lab.SensorDrivers.warm_cameras','host_materialize','cpu_owned_copy')},'buffer_contract':r['buffer_contract'],
 'native_available':r['native']['available'],'clock_alignment':r['native'].get('clock_alignment'),
 'gpu_metric_schema':r['native'].get('gpu_metric_schema'),'metric_catalog':r['native'].get('metric_catalog'),
 'gpu_metrics':r['native'].get('gpu_metrics'),'gpu_metric_row_count':r['native'].get('gpu_metric_row_count'),
 'native_stages':r['native'].get('stages'),'diagnostics_health':r['diagnostics_health']},indent=2))
