import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Kit not stopped')
 except OSError:pass
case=out/'native_pause_no_probe';case.mkdir(exist_ok=False)
spec=json.loads((out/'native/round_01/input_spec.json').read_text());spec.update(freeze_method='pause',pause_after_step=True,timeout_s=600)
(case/'input_spec.json').write_text(json.dumps(spec,indent=2))
with (case/'supervisor.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(R/'native/run.py'),'--config',str(case/'input_spec.json'),'--output',str(case/'capture')],cwd=R/'native',stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({'pid':p.pid,'directory':str(case)}))
