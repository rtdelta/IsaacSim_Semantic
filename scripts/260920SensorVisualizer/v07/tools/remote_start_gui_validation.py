"""Start final GUI smoke after all earlier owned engines have exited."""
import json
import subprocess
import os
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=path.read_bytes()
    except OSError:continue
    if b'/kit/kit' in raw:raise RuntimeError('An existing Kit process was found; preserve it before GUI validation')
unit=subprocess.run(['/usr/bin/python3','-B','-m','unittest','discover','-s','tests','-q'],cwd=root,capture_output=True,text=True,timeout=30)
(root/'reports/linux_unit_tests.json').write_text(json.dumps({'exit_code':unit.returncode,'stdout':unit.stdout,'stderr':unit.stderr},indent=2))
assert unit.returncode==0,unit.stderr[-6000:]
with (root/'reports/native_validation_supervisor.log').open('ab') as log:
    child=subprocess.Popen(['/usr/bin/python3','-B',str(root/'tools/gui_smoke.py')],cwd=root,
        env={**os.environ,'SV07_GUI_SHORT':'1'},
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
info={'pid':child.pid,'start_ticks':Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19]}
(root/'reports/native_validation_process.json').write_text(json.dumps(info,indent=2))
print(json.dumps({'linux_unit_tests':unit.stderr[-200:],'gui_validation':info}))
