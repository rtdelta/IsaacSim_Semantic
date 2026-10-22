"""Narrow diagnostics: legacy reader binding; native warmup and freeze policy."""
import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
def kits():
 for p in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):return True
  except OSError:pass
 return False
results=[]
for label,family,changes in [('legacy_raw_retry1','legacy',{'nc006_raw_probe':True}),('native_warm128','native',{'warm_subframes':128,'measure_frames':1}),('native_pause','native',{'freeze_method':'pause','pause_after_step':True,'measure_frames':1})]:
 if kits():raise RuntimeError('Existing Kit was not stopped')
 case=out/label;case.mkdir(exist_ok=False)
 spec=json.loads((out/family/'round_01/input_spec.json').read_text());spec.update(changes);spec['timeout_s']=600
 path=case/'input_spec.json';path.write_text(json.dumps(spec,indent=2))
 if family=='legacy':args=['/usr/bin/python3','-u','-m','lab.runner','--spec',str(path),'--output',str(case/'capture')];cwd=R/'legacy'
 else:args=['/usr/bin/python3','-u',str(R/'native_dual/run.py'),'--config',str(path),'--output',str(case/'capture')];cwd=R/'native_dual'
 with (case/'supervisor.log').open('xb') as log:
  p=subprocess.Popen(args,cwd=cwd,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
  (out/'causal_progress.json').write_text(json.dumps({'current':label,'pid':p.pid,'completed':results},indent=2));rc=p.wait()
 results.append({'case':label,'exit_code':rc,'limits':'Diagnostic variation; validator failure retained, not accepted as a production capture.'})
 (out/'causal_progress.json').write_text(json.dumps({'current':None,'completed':results,'finished':len(results)==3},indent=2))
