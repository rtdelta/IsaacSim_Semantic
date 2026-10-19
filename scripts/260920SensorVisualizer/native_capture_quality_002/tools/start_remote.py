import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
for f in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=f.read_bytes()
  if args.split(b'\0')[0].endswith(b'/kit/kit') or b'native_capture_quality_002/run.py' in args:raise RuntimeError('Existing experiment or Isaac detected; not stopped')
 except OSError:pass
out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002');out.mkdir(exist_ok=True)
stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime());directory=out/('smoke_'+stamp)
with (out/(directory.name+'.runner.log')).open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'run.py'),'--config',str(root/'config/baseline.json'),'--output',str(directory)],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
info={'pid':p.pid,'directory':str(directory)};(root/'reports/latest_execution.json').write_text(json.dumps(info,indent=2));print(json.dumps(info))
