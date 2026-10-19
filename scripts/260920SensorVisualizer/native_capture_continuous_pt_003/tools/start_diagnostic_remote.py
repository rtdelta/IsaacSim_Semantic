import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Isaac process was not stopped')
 except OSError:pass
spec=json.loads((root/'config/baseline.json').read_text());spec.update(pt_total_spp=128,measure_frames=2,native_preview_initialization=True)
out=Path('/root/gpufree-data/semantic/output/native_capture_continuous_pt_003')/('diagnostic_preview_pt128_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
config=root/'reports/diagnostic_preview.json';config.write_text(json.dumps(spec,indent=2))
with out.with_suffix('.runner.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'run.py'),'--config',str(config),'--output',str(out)],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
info={'pid':p.pid,'directory':str(out)};(root/'reports/latest_execution.json').write_text(json.dumps(info,indent=2));print(json.dumps(info))
