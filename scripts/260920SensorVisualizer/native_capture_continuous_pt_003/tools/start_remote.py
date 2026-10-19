import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Isaac process was not stopped')
 except OSError:pass
out=Path('/root/gpufree-data/semantic/output/native_capture_continuous_pt_003')/('continuous_pt1024_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
out.parent.mkdir(exist_ok=True)
with out.with_suffix('.runner.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'run.py'),'--output',str(out)],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
info={'pid':p.pid,'directory':str(out)};(root/'reports/latest_execution.json').write_text(json.dumps(info,indent=2))
print(json.dumps(info))
