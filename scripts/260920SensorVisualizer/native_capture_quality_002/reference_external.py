"""External unchanged single06 reference, never imported by native engine code.

Uses the preserved experiment CLI in another process. Only its input/output live
in NC-002. Original code and USD are hash checked by deployment/final verification.
"""
import json,subprocess,time,copy,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'single06_lab'
BASE=Path('/root/gpufree-data/semantic/output/native_capture_quality_002')
out=BASE/('reference_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()));out.mkdir(exist_ok=False)
config=json.loads((ROOT/'config/baseline.json').read_text());source=Path(config['trajectory']).parent
traj=out/'source_trajectory';traj.mkdir();meta=json.loads((source/'metadata.json').read_text())
states=[json.loads(l) for l in (source/'states.jsonl').read_text().splitlines() if l.strip()]
for row in states:row['joints_deg']={name:0. for name in row['joints_deg']}
(traj/'states.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in states));(traj/'metadata.json').write_text(json.dumps(meta,indent=2))
(ROOT/'reports/latest_reference.json').write_text(json.dumps({'pid':os.getpid(),'directory':str(out)},indent=2))
results=[]
for repeat in range(3):
 for policy in (('gated','keepalive') if repeat%2==0 else ('keepalive','gated')):
  name=f'{repeat}_{policy}';directory=out/name;spec={'name':name,'pose':'static','trajectory':str(traj),'groups':6,'timeout_s':600,'policy':policy}
  spec_path=out/(name+'.json');spec_path.write_text(json.dumps(spec,indent=2))
  with (out/(name+'.log')).open('xb') as log:
   code=subprocess.run(['/usr/bin/python3','-u','-m','lab.runner','--spec',str(spec_path),'--output',str(directory)],cwd=OLD,stdin=subprocess.DEVNULL,stdout=log,stderr=log).returncode
  results.append({'repeat':repeat,'policy':policy,'exit_code':code,'directory':str(directory)})
  (out/'reference_progress.json').write_text(json.dumps(results,indent=2))
  if code:break
 if results[-1]['exit_code']:break
(out/'reference_result.json').write_text(json.dumps(results,indent=2))
