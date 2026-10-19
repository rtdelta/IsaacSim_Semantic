"""Index/benchmark the finished production bag, preserving all outputs."""
import json, subprocess, sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text())
capture=Path(latest['directory'])/'capture'
result=json.loads((capture/'result.json').read_text())
assert result['exit_code']==0 and result['validation']['passed'] and result['validation']['groups']==300
session=Path(result['capture']['session'])
code="""import json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);capture=Path(sys.argv[2]);session=Path(sys.argv[3])
commands=[['/usr/bin/python3',str(root/'verify_model.py'),str(capture)],['/usr/bin/python3',str(root/'run_viewer.py'),'--capture',str(session),'--index-only'],['/usr/bin/python3',str(root/'run_viewer.py'),'--capture',str(session),'--port','8769','--domain-id','55','--play','--exit-after-end']]
results=[]
for args in commands:
    child=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=240)
    results.append({'argv':args,'exit_code':child.returncode,'stdout':child.stdout[-5000:],'stderr':child.stderr[-3000:]})
    (root/'reports/final_tests.json').write_text(json.dumps(results,indent=2))
    if child.returncode:sys.exit(1)
"""
log=(root/'reports/final_tests.log').open('wb')
child=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','test','/usr/bin/python3','-c',code,str(root),str(capture),str(session)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/'reports/final_tests_pid.json').write_text(json.dumps({'pid':child.pid,'session':str(session)}))
print(json.dumps({'pid':child.pid,'session':str(session),'log':str(root/'reports/final_tests.log')}))
