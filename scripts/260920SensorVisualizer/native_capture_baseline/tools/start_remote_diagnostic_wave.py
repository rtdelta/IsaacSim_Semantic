import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
previous=json.loads((root/'reports/latest_execution.json').read_text());directory=Path(previous['directory'])
result=json.loads((directory/'wave_progress.json').read_text())
if result['state']!='completed':raise RuntimeError('Ordinary wave did not complete')
out=Path('/root/gpufree-data/semantic/output/native_capture_baseline')
with (out/('diagnostic_start_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())+'.log')).open('xb') as f:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'wave.py'),'diagnostic'],cwd=root,
   stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
print(json.dumps({'wave_pid':p.pid,'suite':'diagnostic'}))
