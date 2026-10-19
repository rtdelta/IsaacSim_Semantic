import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
for f in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=f.read_bytes()
  if args.split(b'\0')[0].endswith(b'/kit/kit') or b'native_capture_quality_002/run.py' in args:raise RuntimeError('Existing Isaac detected; not stopped')
 except OSError:pass
log=Path('/root/gpufree-data/semantic/output/native_capture_quality_002')/('default_trace_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())+'.log')
with log.open('xb') as handle:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'wave.py'),'trace'],cwd=root,stdin=subprocess.DEVNULL,stdout=handle,stderr=handle,start_new_session=True)
print(json.dumps({'pid':p.pid,'log':str(log)}))
