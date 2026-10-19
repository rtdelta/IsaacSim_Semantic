"""Create an independent 007 version from the preserved 006 baseline once."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2];OLD=ROOT/'tools/native_instant_baseline';NEW=Path(__file__).parent
records=[]
for name in ('io.py','runtime.py','math_independent.py','run_minimal.py','analyze_independent.py'):
 data=(OLD/name).read_bytes();records.append({'source':str((OLD/name).relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest()})
 target=NEW/('run_layers.py' if name=='run_minimal.py' else name)
 if target.exists():raise RuntimeError('independent target already exists '+str(target))
 target.write_text(data.decode('utf-8').replace('tools.native_instant_baseline','tools.native_rotation_localization'),encoding='utf-8')
(NEW/'baseline_provenance.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print('Created independent copies; locked baseline unchanged')
