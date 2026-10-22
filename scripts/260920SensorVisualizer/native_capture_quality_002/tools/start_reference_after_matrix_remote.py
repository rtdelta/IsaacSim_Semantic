"""Queue preserved-reference CLI only after this task's matrix exits."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
matrix=json.loads((root/'reports/latest_matrix.json').read_text())
code='''import json,time,subprocess
from pathlib import Path
root=Path(ROOT);matrix=json.loads((root/'reports/latest_matrix.json').read_text())
deadline=time.monotonic()+2400
while Path('/proc/'+str(matrix['pid'])).exists():
 if time.monotonic()>deadline:raise TimeoutError('Matrix queue exceeded its deadline')
 time.sleep(1)
rows=json.loads((Path(matrix['directory'])/'matrix_result.json').read_text())
if not any(r['suite']=='rt' and r['exit_code']==0 for r in rows):raise RuntimeError('Native RT matrix invalid; fair reference not launched')
raise SystemExit(subprocess.run(['/usr/bin/python3','-u',str(root/'reference_external.py')],cwd=root,stdin=subprocess.DEVNULL).returncode)
'''.replace('ROOT',repr(str(root)))
runner=root/'reports/queued_reference.py'
if runner.exists():raise FileExistsError(str(runner))
runner.write_text(code)
out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002');log=out/('queued_reference_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())+'.log')
with log.open('xb') as handle:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(runner)],cwd=root,stdin=subprocess.DEVNULL,stdout=handle,stderr=handle,start_new_session=True)
print(json.dumps({'pid':p.pid,'log':str(log),'wait_for_matrix_pid':matrix['pid']}))
