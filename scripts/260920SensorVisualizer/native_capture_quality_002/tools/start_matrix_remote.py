import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
for f in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=f.read_bytes()
  if args.split(b'\0')[0].endswith(b'/kit/kit') or b'native_capture_quality_002/run.py' in args or b'native_capture_quality_002/matrix.py' in args:raise RuntimeError('Existing capture detected; not stopped')
 except OSError:pass
stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime());out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002')
with (out/('matrix_'+stamp+'.runner.log')).open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'matrix.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'pid':p.pid,'runner_log':str(out/('matrix_'+stamp+'.runner.log'))}))
