from pathlib import Path
import json,os,subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
pointer=root/'reports/latest_test.json'
headless=root/'reports/latest_headless_test.json'
if headless.exists() and headless.stat().st_mtime>pointer.stat().st_mtime:pointer=headless
out=Path(json.loads(pointer.read_text())['directory'])
if (out/'acceptance.json').exists():report=json.loads((out/'acceptance.json').read_text())
else:report={'captures':[{'name':'headless_cli','session':str(p.parent)} for p in (out/'captures').glob('*/session.json')]}
results=[]
env=os.environ.copy()
for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
for capture in report['captures']:
    session=Path(capture['session'])
    cmd=['/bin/bash','--noprofile','--norc','-c',
         'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','sv04-validate',
         str(root/'tools/validate_capture.py'),str(session),'--export-images']
    result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=90)
    entry={'name':capture['name'],'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr[-4000:]}
    results.append(entry)
(out/'validation_results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
