"""Start a bounded native steady-state trace with existing 1 kHz GPU metrics."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab')
out=Path('/root/gpufree-data/semantic/output/single06_lab');out.mkdir(exist_ok=True)
stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime());directory=out/('trace_steady_'+stamp)
spec={'name':'trace_steady','groups':2,'policy':'gated','pose':'moving',
 'trace_window':'steady','trace_group':1,'metrics_set':'ad10x','metrics_hz':1000,
 'trajectory':'/root/gpufree-data/semantic/output/sensor_visualizer/v06/benchmarks/1791604257379431843_v05/input_trajectory'}
spec_path=out/(directory.name+'_spec.json');spec_path.write_text(json.dumps(spec))
with (out/(directory.name+'_supervisor.log')).open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u','-m','lab.runner','--spec',str(spec_path),'--output',str(directory)],
   cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
record={'pid':p.pid,'directory':str(directory),'kind':'trace_steady'}
(root/'reports/latest_execution.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
