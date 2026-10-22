"""Read scoped reports and owned test warnings without importing Kit."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
directory=root/'reports/native_owner';owner=json.loads((directory/'owner.json').read_text())
reports={}
for name in ('native_keyboard_fix','lifecycle_fix','interaction','validation_offline'):
    p=directory/(name+'.json')
    if p.exists():reports[name]=json.loads(p.read_text())
log=Path(owner['log']).read_text(errors='replace')
errors=[line for line in log.splitlines() if any(s in line for s in ('Traceback','AttributeError','RuntimeError','AssertionError','SV06 NATIVE EVENT TEST'))]
print(json.dumps({'reports':reports,'test_process_exists':Path('/proc/'+str(owner['pid'])).exists(),
    'relevant_log_lines':errors[-15:]},ensure_ascii=False))
