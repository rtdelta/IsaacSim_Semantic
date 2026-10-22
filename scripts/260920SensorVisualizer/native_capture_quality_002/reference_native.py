"""Three identical six-group native rounds; PNG export excluded explicitly."""
import json,subprocess,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002')/('reference_native_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()));out.mkdir(exist_ok=False)
(ROOT/'reports/latest_native_reference.json').write_text(json.dumps({'pid':os.getpid(),'directory':str(out)},indent=2));rows=[]
for repeat in range(3):
 spec=json.loads((ROOT/'config/baseline.json').read_text());spec.update(experiment='reference',export_quality_images=False,reference_repeat=repeat)
 cfg=out/(str(repeat)+'.json');cfg.write_text(json.dumps(spec,indent=2));directory=out/str(repeat)
 with (out/(str(repeat)+'.log')).open('xb') as log:
  code=subprocess.run(['/usr/bin/python3','-u',str(ROOT/'run.py'),'--config',str(cfg),'--output',str(directory)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log).returncode
 rows.append({'repeat':repeat,'directory':str(directory),'exit_code':code});(out/'reference_native_progress.json').write_text(json.dumps(rows,indent=2))
 if code:break
(out/'reference_native_result.json').write_text(json.dumps(rows,indent=2))
