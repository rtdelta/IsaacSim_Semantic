"""Launch exactly one owned, bounded native smoke test."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
out=Path('/root/gpufree-data/semantic/output/native_capture_baseline');out.mkdir(exist_ok=True)
name='smoke_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime());directory=out/name
with (out/(name+'.log')).open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'run.py'),'--mode','record','--frames','12','--warmup','8','--output',str(directory)],
   cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
record={'pid':p.pid,'directory':str(directory),'kind':'smoke'}
(root/'reports/latest_execution.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
