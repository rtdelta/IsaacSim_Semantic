import json,subprocess,time,urllib.request
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
print((root/'reports/isolated_gui.log').read_text()[-3000:])
req=urllib.request.Request('http://127.0.0.1:8770/api/control',data=b'{"action":"seek","group":150}',headers={'Content-Type':'application/json'})
assert urllib.request.urlopen(req,timeout=5).status==202
time.sleep(2)
result=subprocess.run(['/usr/bin/python3',str(root/'screenshot_rviz.py'),str(root/'reports/rviz_isolated_frame150.png'),'--display',':88'],capture_output=True,text=True,timeout=20)
print(json.dumps({'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'status':json.load(urllib.request.urlopen('http://127.0.0.1:8770/api/status',timeout=5))}))
assert result.returncode==0
