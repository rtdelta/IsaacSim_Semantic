import hashlib,json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
assert json.loads((out/'progress.json').read_text())['state']=='completed'
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Kit was not stopped')
 except OSError:pass
case=out/'native_dual_retry1';case.mkdir(exist_ok=False)
spec=json.loads((out/'native/round_01/input_spec.json').read_text());spec['motion_profile']='NC006_same_product_dual_exit';spec['timeout_s']=600
(case/'input_spec.json').write_text(json.dumps(spec,indent=2))
with (case/'supervisor.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(R/'native_dual/run.py'),'--config',str(case/'input_spec.json'),'--output',str(case/'capture')],cwd=R/'native_dual',stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'dual_pid':p.pid,'directory':str(case)}))

