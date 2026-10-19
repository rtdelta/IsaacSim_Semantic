"""Run the second measured-evidence wave after the first wave fully exits."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab')
out=Path('/root/gpufree-data/semantic/output/single06_lab')/('followup_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
with out.with_suffix('.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'tools/run_followup.py'),'--output',str(out)],
   cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
record={'pid':p.pid,'directory':str(out),'kind':'followup'}
(root/'reports/latest_execution.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
