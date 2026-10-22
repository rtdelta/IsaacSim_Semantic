import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
code='''import json,time,subprocess
from pathlib import Path
root=Path(ROOT);deadline=time.monotonic()+2400
while not (root/'reports/latest_reference.json').exists():
 if time.monotonic()>deadline:raise TimeoutError('Reference did not start')
 time.sleep(1)
old=json.loads((root/'reports/latest_reference.json').read_text())
while Path('/proc/'+str(old['pid'])).exists():
 if time.monotonic()>deadline:raise TimeoutError('Reference did not finish')
 time.sleep(1)
raise SystemExit(subprocess.run(['/usr/bin/python3','-u',str(root/'reference_native.py')],cwd=root,stdin=subprocess.DEVNULL).returncode)
'''.replace('ROOT',repr(str(root)))
runner=root/'reports/queued_native_reference.py'
if runner.exists():raise FileExistsError(str(runner))
runner.write_text(code)
out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002');log=out/('queued_native_reference_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime())+'.log')
with log.open('xb') as handle:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(runner)],cwd=root,stdin=subprocess.DEVNULL,stdout=handle,stderr=handle,start_new_session=True)
print(json.dumps({'pid':p.pid,'log':str(log)}))
