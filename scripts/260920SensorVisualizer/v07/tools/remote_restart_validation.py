"""Run only v07 after retaining the completed same-instance baseline."""
import json
import os
import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
previous=json.loads((root/'reports/native_validation_result.json').read_text())
assert previous['state'] in ('passed','failed')
directory=Path(previous['directory'])
assert directory.is_relative_to(Path('/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation'))
(directory/'validation_result.json').write_text(json.dumps(previous,indent=2))
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=path.read_bytes()
    except OSError:continue
    if b'/kit/kit' in raw:raise RuntimeError('A Kit process still exists; preserve it and wait for owned cleanup')
unit=subprocess.run(['/usr/bin/python3','-B','-m','unittest','discover','-s','tests','-q'],cwd=root,capture_output=True,text=True,timeout=30)
(root/'reports/linux_unit_tests.json').write_text(json.dumps({'exit_code':unit.returncode,'stdout':unit.stdout,'stderr':unit.stderr},indent=2))
assert unit.returncode==0,unit.stderr[-6000:]
env=os.environ.copy();env['SV07_SKIP_BASELINE']='1'
with (root/'reports/native_validation_supervisor.log').open('ab') as log:
    child=subprocess.Popen(['/usr/bin/python3','-B',str(root/'tools/native_validation.py')],cwd=root,
        env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
info={'pid':child.pid,'start_ticks':Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19],
      'log':str(root/'reports/native_validation_supervisor.log')}
(root/'reports/native_validation_process.json').write_text(json.dumps(info,indent=2))
print(json.dumps({'linux_unit_tests':'passed','tests':unit.stderr[-250:],'validation':info}))
