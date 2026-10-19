"""Start one reviewed ordinary experiment wave after native smoke success."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
previous=json.loads((root/'reports/latest_execution.json').read_text());directory=Path(previous['directory'])
result=json.loads((directory/'result.json').read_text())
if result['state']!='completed':raise RuntimeError('Previous smoke did not pass')
out=Path('/root/gpufree-data/semantic/output/native_capture_baseline')
log=out/('wave_start_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())+'.log')
with log.open('xb') as f:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'wave.py'),'ordinary'],cwd=root,
   stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
print(json.dumps({'wave_pid':p.pid,'log':str(log)}))
