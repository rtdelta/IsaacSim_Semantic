"""Start a bounded owned confirmation wave after previous execution exits."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab')
previous=json.loads((root/'reports/latest_execution.json').read_text())
if Path('/proc',str(previous['pid'])).exists():raise RuntimeError('Previous owned supervisor still running')
out=Path('/root/gpufree-data/semantic/output/single06_lab')/('confirmation_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
with out.with_suffix('.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'tools/run_confirmation.py'),'--output',str(out)],
   cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
record={'pid':p.pid,'directory':str(out),'kind':'confirmation'}
(root/'reports/latest_execution.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
