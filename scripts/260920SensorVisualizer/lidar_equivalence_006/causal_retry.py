"""One-group controls with matching, explicitly shortened input trajectory."""
import json,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
def idle():
 for p in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Unexpected existing Kit')
  except OSError:pass
rows=[]
for label,changes in [('native_warm128_retry1',{'warm_subframes':128}),('native_pause_retry1',{'freeze_method':'pause','pause_after_step':True})]:
 idle();case=out/label;case.mkdir(exist_ok=False)
 spec=json.loads((out/'native/round_01/input_spec.json').read_text());spec.update(changes,measure_frames=1,timeout_s=600)
 trajectory=case/'one_state.jsonl';trajectory.write_text(Path(spec['trajectory']).read_text().splitlines()[0]+'\n')
 spec.update(trajectory=str(trajectory),trajectory_sha256=hashlib.sha256(trajectory.read_bytes()).hexdigest())
 path=case/'input_spec.json';path.write_text(json.dumps(spec,indent=2))
 with (case/'supervisor.log').open('xb') as log:
  p=subprocess.Popen(['/usr/bin/python3','-u',str(R/'native_dual/run.py'),'--config',str(path),'--output',str(case/'capture')],cwd=R/'native_dual',stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
  (out/'causal_retry_progress.json').write_text(json.dumps({'current':label,'pid':p.pid,'completed':rows},indent=2));rc=p.wait()
 rows.append({'case':label,'exit_code':rc});(out/'causal_retry_progress.json').write_text(json.dumps({'current':None,'completed':rows,'finished':len(rows)==2},indent=2))
