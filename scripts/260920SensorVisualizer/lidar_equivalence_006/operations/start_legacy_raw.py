import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
assert json.loads((out/'progress.json').read_text())['state']=='completed'
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Kit was not stopped')
 except OSError:pass
case=out/'legacy_raw';case.mkdir(exist_ok=False)
spec=json.loads((out/'legacy/round_01/input_spec.json').read_text());spec.update(nc006_raw_probe=True,name='NC006_raw_legacy')
(case/'input_spec.json').write_text(json.dumps(spec,indent=2))
with (case/'supervisor.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u','-m','lab.runner','--spec',str(case/'input_spec.json'),'--output',str(case/'capture')],cwd=R/'legacy',stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'pid':p.pid,'directory':str(case)}))
