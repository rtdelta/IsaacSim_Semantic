import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
previous=json.loads((root/'reports/latest_execution.json').read_text());directory=Path(previous['directory'])
if json.loads((directory/'wave_progress.json').read_text())['state']!='completed':raise RuntimeError('Previous wave still incomplete')
out=Path('/root/gpufree-data/semantic/output/native_capture_baseline')
with (out/('final_start_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())+'.log')).open('xb') as f:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'wave.py'),'final'],cwd=root,
   stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
print(json.dumps({'wave_pid':p.pid,'suite':'final'}))
