"""Sequential, audited test queue; never runs two Isaac processes together."""
import json,subprocess,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002')/('matrix_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
out.mkdir(exist_ok=False);rows=[]
(ROOT/'reports/latest_matrix.json').write_text(json.dumps({'pid':os.getpid(),'directory':str(out)},indent=2))
for suite in ('rt','pt','trace','control'):
 with (out/(suite+'.log')).open('xb') as log:
  code=subprocess.run(['/usr/bin/python3','-u',str(ROOT/'wave.py'),suite],stdin=subprocess.DEVNULL,stdout=log,stderr=log,cwd=ROOT).returncode
 execution=json.loads((ROOT/'reports/latest_execution.json').read_text());rows.append({'suite':suite,'exit_code':code,**execution})
 (out/'matrix_progress.json').write_text(json.dumps(rows,indent=2))
 if code and suite=='rt':break
(out/'matrix_result.json').write_text(json.dumps(rows,indent=2))
