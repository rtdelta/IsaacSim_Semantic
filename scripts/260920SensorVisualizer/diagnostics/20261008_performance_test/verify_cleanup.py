from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/output/sensor_visualizer/diagnostics')
r={}
for name in ('20261008_perf_01','20261008_perf_02'):
    d=root/name
    record=json.loads((d/'process.json').read_text())
    result=json.loads((d/'supervisor_result.json').read_text())
    r[name]={'pid':record['pid'],'pid_exists':Path('/proc',str(record['pid'])).exists(),'result':result}
print(json.dumps(r))
